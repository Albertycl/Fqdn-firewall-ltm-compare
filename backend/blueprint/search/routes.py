from flask import Blueprint, request, jsonify, current_app, copy_current_request_context
from model import (db, SearchHistory, LtmVirtualServer, LtmPool, LtmNode,
                   FirewallAddressObject, FirewallAddressGroup, FirewallVipGroup, FirewallPolicy, FirewallNatPolicy, ConfigFile)
import ipaddress
import json
import logging
import os
import re
import time
import pymysql
from concurrent.futures import ThreadPoolExecutor, as_completed


# The FQDN database is a supplementary source. When it is unreachable — a
# different site, or a network that cannot route to it — every search would
# otherwise pay the connect timeout three times over. Remember a failure and
# skip it for a while instead.
_FQDN_DB_DOWN_UNTIL = 0.0


def fqdn_db_available():
    """False when disabled by configuration, or known-down after a recent failure."""
    if os.getenv('FQDN_DB_ENABLED', 'true').lower() not in ('1', 'true', 'yes'):
        return False
    return time.time() >= _FQDN_DB_DOWN_UNTIL


def fqdn_db_connection():
    """Connect to the supplementary FQDN database.

    Host and credentials come from the environment so this is not tied to one
    site, and both timeouts are set explicitly: without them an unreachable host
    hangs each call until the OS TCP timeout, and this runs three times per
    search (~50 s on a network that cannot reach it).

    Raises if the database is disabled or recently failed, so callers — which
    already treat FQDN data as optional — degrade immediately instead of waiting.
    """
    global _FQDN_DB_DOWN_UNTIL

    if not fqdn_db_available():
        raise pymysql.err.OperationalError(2003, 'FQDN database unavailable (disabled or recently unreachable)')

    timeout = int(os.getenv('FQDN_DB_TIMEOUT', '3'))
    try:
        conn = pymysql.connect(
            host=os.getenv('FQDN_DB_HOST') or os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('FQDN_DB_PORT') or os.getenv('DB_PORT', '3306')),
            user=os.getenv('FQDN_DB_USER') or os.getenv('DB_USER', 'root'),
            password=os.getenv('FQDN_DB_PASSWORD') or os.getenv('DB_PASSWORD', ''),
            database=os.getenv('FQDN_DB_NAME', 'fqdn_v3'),
            charset='utf8mb4',
            connect_timeout=timeout,
            read_timeout=timeout,
        )
        _FQDN_DB_DOWN_UNTIL = 0.0
        return conn
    except Exception:
        cooldown = int(os.getenv('FQDN_DB_COOLDOWN', '60'))
        _FQDN_DB_DOWN_UNTIL = time.time() + cooldown
        logger.warning(f"FQDN database unreachable; skipping it for {cooldown}s")
        raise


def is_partial_ip(query):
    """Check if the query is a partial IP (like 172.30, 10.1.2)"""
    import re
    # Pattern for partial IP: 1-3 octets with dots
    partial_ip_pattern = r'^(?:\d{1,3}\.){1,3}\d{1,3}?$'
    # Full IP pattern
    full_ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    
    return re.match(partial_ip_pattern, query) and not re.match(full_ip_pattern, query)

def build_partial_ip_conditions(query, field, partial_match=True):
    """Build database conditions for IP search (exact or partial)"""
    conditions = []
    
    if is_partial_ip(query):
        # For partial IPs like "172.30", search for "172.30.%"
        conditions.append(field.like(f"{query}.%"))
        conditions.append(field.like(f"%/{query}.%"))  # Handle F5 /Common/ prefix
    else:
        # For complete IPs, use exact match
        conditions.append(field == query)
        conditions.append(field.like(f"%/{query}"))  # Handle F5 /Common/ prefix
    
    return conditions

logger = logging.getLogger(__name__)

search_bp = Blueprint('search', __name__, url_prefix='/api/search')

def is_ip_in_subnet(ip, subnet):
    """Check if an IP address is within a subnet"""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(subnet, strict=False)
    except Exception:
        return False

def is_ip_in_cidr_or_exact(search_ip, target_cidr_or_ip):
    """
    Check if search_ip matches target using exact match or CIDR subnet matching.

    Args:
        search_ip: IP address to search for (e.g., "203.0.113.8")
        target_cidr_or_ip: Target IP/CIDR (e.g., "203.0.113.8/29" or "203.0.113.8")

    Returns:
        True if search_ip matches target exactly or is within target's subnet

    Examples:
        is_ip_in_cidr_or_exact("203.0.113.8", "203.0.113.8/29") → True
        is_ip_in_cidr_or_exact("203.0.113.8", "203.0.113.8") → True
        is_ip_in_cidr_or_exact("203.0.113.8", "203.0.113.80/29") → False
        is_ip_in_cidr_or_exact("203.0.113.8", "203.0.113.88") → False
    """
    target_str = str(target_cidr_or_ip)

    # Handle CIDR notation (e.g., "203.0.113.8/29")
    if '/' in target_str:
        # Extract base IP and prefix
        try:
            # For /32, check exact match first (optimization)
            if target_str.endswith('/32'):
                target_ip = target_str.rsplit('/', 1)[0]
                return search_ip == target_ip

            # For other CIDR ranges, use subnet matching
            return is_ip_in_subnet(search_ip, target_str)
        except Exception:
            return False

    # No CIDR notation - exact IP match only
    return search_ip == target_str

def get_infrastructure_config_file_ids(infrastructure_filter=None):
    """Get config file IDs filtered by infrastructure"""
    from sqlalchemy import func, desc

    # Get the latest config file for each distinct config type
    latest_config_files = db.session.query(
        func.max(ConfigFile.id).label('max_id'),
        func.regexp_replace(ConfigFile.filename, r'_\d{8}-\d{4}\.txt$', '').label('config_pattern')
    ).group_by(func.regexp_replace(ConfigFile.filename, r'_\d{8}-\d{4}\.txt$', '')).all()

    latest_config_file_ids = [cf.max_id for cf in latest_config_files]

    # If no infrastructure filter, return all
    if not infrastructure_filter or len(infrastructure_filter) == 0:
        return latest_config_file_ids

    # Filter by infrastructure
    filtered_ids = []
    infrastructure_mapping = {
        'DELTA': ['DELTA-LTM', 'DELTA-FW01_', 'DELTA-ADMIN-FW01'],
        'CHARLIE': ['CHARLIE-LTM', 'CHARLIE-FW01'],
        'BRAVO': ['BRAVO-LTM', 'BRAVO-FW01'],
        'ALPHA': ['ALPHA-FW01', 'ALPHA-LTM01'],
        'ADMIN': ['ADMIN-LTM', 'ADMIN-FW01'],
        'UAT': ['UAT-FW01', 'UAT-SLB01'],
        'LOADTEST': ['LoadTest-FW01', 'LoadTest-LTM01']
    }

    # Get all config files and filter by infrastructure
    config_files = ConfigFile.query.filter(ConfigFile.id.in_(latest_config_file_ids)).all()

    for config_file in config_files:
        for infra_key in infrastructure_filter:
            if infra_key in infrastructure_mapping:
                patterns = infrastructure_mapping[infra_key]
                for pattern in patterns:
                    if pattern in config_file.filename:
                        filtered_ids.append(config_file.id)
                        break

    return filtered_ids

def expand_cidr_ranges(ip_list):
    """Expand CIDR ranges to individual IP addresses"""
    expanded_ips = set()

    for ip_entry in ip_list:
        try:
            # Clean up the IP (remove /Common/ prefix if present)
            clean_ip = ip_entry.replace('/Common/', '') if ip_entry else ''

            # Check if it's a CIDR range
            if '/' in clean_ip:
                try:
                    # Parse as network
                    network = ipaddress.ip_network(clean_ip, strict=False)
                    # Add all individual IPs in the range (limit to reasonable size)
                    if network.num_addresses <= 256:  # Limit to avoid huge ranges
                        if network.num_addresses <= 16:  # For small networks like /28, /29, /30
                            # Include network, all hosts, and broadcast addresses
                            expanded_ips.add(str(network.network_address))
                            for ip in network.hosts():
                                expanded_ips.add(str(ip))
                            expanded_ips.add(str(network.broadcast_address))
                        else:
                            # For larger networks, just include host addresses
                            for ip in network.hosts():
                                expanded_ips.add(str(ip))
                    else:
                        # For large ranges, just add the network address
                        expanded_ips.add(str(network.network_address))
                except ValueError:
                    # Not a valid CIDR, treat as regular IP
                    expanded_ips.add(clean_ip)
            else:
                # Regular IP address
                expanded_ips.add(clean_ip)
        except Exception as e:
            logger.warning(f"Error processing IP {ip_entry}: {e}")
            continue

    return list(expanded_ips)

def search_ltm_configs(ip_address, search_direction='both', infrastructure_filter=None):
    """Search for IP address in LTM configurations"""
    # Get only the most recent config file for each filename
    # ConfigFile already imported at top
    from sqlalchemy import func, desc
    
    # Get config file IDs filtered by infrastructure (only LTM/SLB files)
    all_filtered_ids = get_infrastructure_config_file_ids(infrastructure_filter)

    # Filter to only include LTM/SLB config files
    ltm_config_files = ConfigFile.query.filter(
        db.and_(
            ConfigFile.id.in_(all_filtered_ids),
            db.or_(
                ConfigFile.filename.like('%LTM%'),  # Standard LTM config files
                ConfigFile.filename.like('H2SLB01%'),  # H2SLB01.TRZ.PRD LTM system (legacy)
                ConfigFile.filename.like('%SLB%')   # Other SLB (Server Load Balancer) systems
            )
        )
    ).all()

    latest_config_file_ids = [cf.id for cf in ltm_config_files]
    
    # Use a dictionary to deduplicate virtual servers by name+destination+port combination
    unique_virtual_servers = {}
    
    # Search in virtual servers (handle F5 /Common/ prefix) - only latest config files
    # Build IP search conditions based on whether it's partial or complete
    ip_conditions = build_partial_ip_conditions(ip_address, LtmVirtualServer.destination_ip)
    
    vs_matches = LtmVirtualServer.query.filter(
        db.and_(
            db.or_(*ip_conditions),
            LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
        )
    ).all()
    
    # Add direct VS matches
    for vs in vs_matches:
        vs_data = vs.serialize
        vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
        
        # Get all nodes for this VS's pool (handle duplicate pools with same name)
        pool_nodes = []
        unique_nodes = {}  # Use dict to deduplicate nodes by ip:port
        if vs.pool_name:
            # Find ALL pools with this name from latest config files only
            pools = LtmPool.query.filter(
                db.and_(
                    LtmPool.name == vs.pool_name,
                    LtmPool.config_file_id.in_(latest_config_file_ids)
                )
            ).all()
            for pool in pools:
                nodes = LtmNode.query.filter(
                    db.and_(
                        LtmNode.pool_id == pool.id,
                        LtmNode.config_file_id.in_(latest_config_file_ids)
                    )
                ).all()
                for node in nodes:
                    # Create unique key for each node: ip_address:port
                    # Same pool can exist in multiple config files, so exclude pool_id from key
                    node_key = f"{node.ip_address}:{node.port}"
                    if node_key not in unique_nodes:
                        unique_nodes[node_key] = node.serialize
            
            pool_nodes = list(unique_nodes.values())
        
        # Create unique key based on name + destination + port to avoid duplicates
        unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
        unique_virtual_servers[unique_key] = {
            'virtual_server': vs_data,
            'pool_nodes': pool_nodes
        }
    
    # Search in nodes directly (handle potential prefixes) - only latest config files
    node_ip_conditions = build_partial_ip_conditions(ip_address, LtmNode.ip_address)
    node_ip_conditions.append(LtmNode.ip_address.like(f"{ip_address}:%"))  # Handle IP:port format
    
    node_matches = LtmNode.query.filter(
        db.and_(
            db.or_(*node_ip_conditions),
            LtmNode.config_file_id.in_(latest_config_file_ids)
        )
    ).all()
    
    # For each matching node, find its pool and associated virtual servers
    for node in node_matches:
        pool = LtmPool.query.filter(
            db.and_(
                LtmPool.id == node.pool_id,
                LtmPool.config_file_id.in_(latest_config_file_ids)
            )
        ).first() if node.pool_id else None
        if pool:
            # Find all virtual servers using this pool - only from latest config files
            virtual_servers = LtmVirtualServer.query.filter(
                db.and_(
                    LtmVirtualServer.pool_name == pool.name,
                    LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
                )
            ).all()
            
            if virtual_servers:
                # If there are virtual servers, add them normally
                for vs in virtual_servers:
                    # Create unique key to avoid duplicates
                    unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
                    # Only add if not already in the results (avoids duplicates)
                    if unique_key not in unique_virtual_servers:
                        vs_data = vs.serialize
                        vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
                        
                        # Get all nodes for this pool - only from latest config files
                        nodes = LtmNode.query.filter(
                            db.and_(
                                LtmNode.pool_id == pool.id,
                                LtmNode.config_file_id.in_(latest_config_file_ids)
                            )
                        ).all()
                        pool_nodes = [node_obj.serialize for node_obj in nodes]
                        
                        unique_virtual_servers[unique_key] = {
                            'virtual_server': vs_data,
                            'pool_nodes': pool_nodes
                        }
            else:
                # If no direct virtual servers found, try to find VS by name pattern matching
                # Pattern: vs22037_CSPTA_Crypto matches po22037_CSPTA_Crypto
                pool_name_clean = pool.name.replace('/Common/', '')
                
                # Try different VS naming patterns
                vs_patterns = []
                if pool_name_clean.startswith('po'):
                    # Try replacing 'po' with 'vs'
                    vs_patterns.append(pool_name_clean.replace('po', 'vs', 1))
                if pool_name_clean.startswith('u-po'):
                    # Try replacing 'u-po' with 'u-vs'
                    vs_patterns.append(pool_name_clean.replace('u-po', 'u-vs', 1))
                
                # Search for virtual servers matching these patterns
                matching_virtual_servers = []
                for pattern in vs_patterns:
                    vs_matches = LtmVirtualServer.query.filter(
                        db.and_(
                            db.or_(
                                LtmVirtualServer.name == pattern,
                                LtmVirtualServer.name == f'/Common/{pattern}'
                            ),
                            LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
                        )
                    ).all()
                    matching_virtual_servers.extend(vs_matches)
                
                if matching_virtual_servers:
                    # Found matching virtual servers by name pattern
                    for vs in matching_virtual_servers:
                        unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
                        if unique_key not in unique_virtual_servers:
                            vs_data = vs.serialize
                            vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
                            vs_data['pool_name'] = pool.name  # Associate with the pool we found
                            
                            # Get all nodes for this pool - only from latest config files
                            nodes = LtmNode.query.filter(
                                db.and_(
                                    LtmNode.pool_id == pool.id,
                                    LtmNode.config_file_id.in_(latest_config_file_ids)
                                )
                            ).all()
                            pool_nodes = [node_obj.serialize for node_obj in nodes]
                            
                            unique_virtual_servers[unique_key] = {
                                'virtual_server': vs_data,
                                'pool_nodes': pool_nodes
                            }
                else:
                    # If still no virtual servers found, create a "standalone node" entry
                    # This shows nodes that exist in pools but have no associated virtual servers
                    unique_key = f"standalone_pool_{pool.name}"
                    if unique_key not in unique_virtual_servers:
                        # Get all nodes for this pool - only from latest config files  
                        nodes = LtmNode.query.filter(
                            db.and_(
                                LtmNode.pool_id == pool.id,
                                LtmNode.config_file_id.in_(latest_config_file_ids)
                            )
                        ).all()
                        pool_nodes = [node_obj.serialize for node_obj in nodes]
                        
                        # Create a virtual entry for standalone pool
                        unique_virtual_servers[unique_key] = {
                            'virtual_server': {
                                'name': f"[Pool Only] {pool.name}",
                                'destination_ip': None,
                                'destination_port': None,
                                'pool_name': pool.name,
                                'enabled': True,
                                'status': 'pool_only',  # Special status for pools without VS
                                'id': None
                            },
                            'pool_nodes': pool_nodes
                        }
    
    # Return only the virtual_servers list (no more pools_and_nodes section)
    results = {
        'virtual_servers': list(unique_virtual_servers.values()),
        'pools_and_nodes': []  # Keep empty for backward compatibility
    }
    
    return results

def resolve_group_members_batch(group_names, max_depth=2, visited=None):
    """Optimized batch resolution of address group members"""
    if visited is None:
        visited = set()
    
    if max_depth <= 0 or not group_names:
        return {}
    
    # Prevent infinite recursion
    group_names = [name for name in group_names if name not in visited]
    if not group_names:
        return {}
    
    visited.update(group_names)
    resolved = {}
    
    # Batch query for address objects
    all_possible_members = set()
    groups_data = {}
    
    # First get all groups and collect member names
    groups = FirewallAddressGroup.query.filter(
        FirewallAddressGroup.name.in_(group_names)
    ).all()
    
    for group in groups:
        if group.members:
            try:
                members = json.loads(group.members) if isinstance(group.members, str) else group.members
                if len(members) > 100:  # Skip very large groups to prevent timeout
                    resolved[group.name] = {'ips': [f"Large Group ({len(members)} members)"], 'member_count': len(members)}
                    continue
                groups_data[group.name] = members
                all_possible_members.update(members)
            except Exception:
                resolved[group.name] = {'ips': [f"Error parsing: {group.name}"], 'member_count': 0}
    
    # Batch query for all address objects
    if all_possible_members:
        address_objects = FirewallAddressObject.query.filter(
            FirewallAddressObject.name.in_(all_possible_members)
        ).all()  # Removed limit to show all results
        
        address_map = {}
        for obj in address_objects:
            display_ip = obj.cidr_notation or obj.ip_address
            if not obj.cidr_notation and obj.ip_address and obj.object_type == 'host':
                display_ip = f"{obj.ip_address}/32"
            address_map[obj.name] = display_ip
    else:
        address_map = {}
    
    # Resolve each group
    for group_name, members in groups_data.items():
        member_ips = []
        nested_groups = []
        
        for member in members:  # Process all members
            if member in address_map:
                member_ips.append(address_map[member])
            else:
                nested_groups.append(member)
        
        # Handle nested groups with reduced depth
        if nested_groups and max_depth > 1:
            nested_resolved = resolve_group_members_batch(nested_groups, max_depth - 1, visited.copy())
            for nested_name, nested_data in nested_resolved.items():
                member_ips.extend(nested_data.get('ips', []))
        
        resolved[group_name] = {
            'ips': member_ips,  # Show all IPs
            'member_count': len(member_ips)
        }
    
    return resolved

def preserve_group_hierarchy_for_policy_display(member_details):
    """
    Preserve group hierarchy for expandable policy display.
    Converts member_details into expandable group structure instead of flattening.
    """
    if not member_details:
        return []

    hierarchical_members = []

    for member in member_details:
        if not member or not isinstance(member, dict):
            continue

        member_type = member.get('type', 'unknown')
        member_name = member.get('name', '')
        member_ip = member.get('ip', '')

        if member_type == 'address':
            # Individual address object - add directly
            hierarchical_members.append({
                'name': member_name,
                'ip': member_ip,
                'type': 'address',
                'display_name': f"{member_name} → {member_ip}"
            })
        elif member_type == 'group':
            # Group - keep as expandable group structure
            nested_members = member.get('nested_members', [])
            if nested_members:
                # Process nested members recursively to maintain hierarchy
                processed_nested = preserve_group_hierarchy_for_policy_display(nested_members)
            else:
                # Try to resolve group from database
                group_name = member_name
                addr_group = FirewallAddressGroup.query.join(ConfigFile).filter(
                    FirewallAddressGroup.name == group_name
                ).order_by(ConfigFile.upload_date.desc()).first()

                if addr_group and addr_group.member_details:
                    try:
                        group_member_details = json.loads(addr_group.member_details)
                        processed_nested = preserve_group_hierarchy_for_policy_display(group_member_details)
                    except Exception:
                        processed_nested = []
                else:
                    processed_nested = []

            # Add group with its nested members
            hierarchical_members.append({
                'name': member_name,
                'ip': member_ip or f"Group with {len(processed_nested)} members",
                'type': 'group',
                'display_name': f"{member_name} → Group with {len(processed_nested)} members",
                'members': processed_nested,
                'member_count': len(processed_nested),
                'expandable': True
            })
        elif member_type == 'missing':
            # Try to resolve missing members from database (cross-file references)
            addr_obj = FirewallAddressObject.query.filter_by(name=member_name).first()
            if addr_obj:
                # Found as address object in another config file - add it as address type
                display_ip = addr_obj.cidr_notation or addr_obj.ip_address
                hierarchical_members.append({
                    'name': member_name,
                    'ip': display_ip,
                    'type': 'address',
                    'display_name': f"{member_name} → {display_ip}"
                })
            else:
                # Check if it's a group in another config file
                addr_group = FirewallAddressGroup.query.filter_by(name=member_name).first()
                if addr_group and addr_group.member_details:
                    try:
                        group_member_details = json.loads(addr_group.member_details)
                        processed_nested = preserve_group_hierarchy_for_policy_display(group_member_details)
                        hierarchical_members.append({
                            'name': member_name,
                            'ip': f"Group with {len(processed_nested)} members",
                            'type': 'group',
                            'display_name': f"{member_name} → Group with {len(processed_nested)} members",
                            'members': processed_nested,
                            'member_count': len(processed_nested),
                            'expandable': True
                        })
                    except Exception:
                        # If resolution fails, add as missing
                        hierarchical_members.append({
                            'name': member_name,
                            'ip': member_ip,
                            'type': member_type,
                            'display_name': f"{member_name} → {member_ip}"
                        })
                else:
                    # Truly missing - add as is
                    hierarchical_members.append({
                        'name': member_name,
                        'ip': member_ip,
                        'type': member_type,
                        'display_name': f"{member_name} → {member_ip}"
                    })
        else:
            # Other types (circular, unknown, etc.) - add as is
            hierarchical_members.append({
                'name': member_name,
                'ip': member_ip,
                'type': member_type,
                'display_name': f"{member_name} → {member_ip}"
            })

    return hierarchical_members

def group_by_prefix_for_policy_display(member_details):
    """
    Group flat address objects by their common prefixes for hierarchical display.
    Example: ext_partner_198.51.100.0_24, ext_partner_203.0.113.0_24 -> ext_partner group
    """
    logger.debug(f"DEBUG: group_by_prefix_for_policy_display called with {len(member_details) if member_details else 0} members")
    if member_details:
        logger.debug(f"DEBUG: First few members: {member_details[:3] if len(member_details) > 3 else member_details}")

    if not member_details:
        return []

    # Dictionary to group members by prefix
    prefix_groups = {}
    ungrouped_members = []

    for member in member_details:
        if not member or not isinstance(member, dict):
            continue

        member_name = member.get('name', '')
        member_ip = member.get('ip', '')
        member_type = member.get('type', 'address')

        # Look for common prefixes (e.g., ext_partner_, ext_Azure_VDI_)
        prefix_found = False

        # Common prefix patterns for grouping
        if '_' in member_name:
            # Try different levels of prefix grouping
            parts = member_name.split('_')
            if len(parts) >= 3:
                # Try grouping by first 3 parts: ext_partner_xxx -> ext_partner
                prefix = '_'.join(parts[:2])
                if prefix.startswith('ext_'):
                    if prefix not in prefix_groups:
                        prefix_groups[prefix] = []
                    # Preserve all original member properties
                    member_copy = member.copy()
                    member_copy.update({
                        'display_name': f"{member_name} → {member_ip}"
                    })

                    # Convert nested_members to expandable format if present
                    if member_copy.get('type') == 'group' and 'nested_members' in member_copy:
                        member_copy['members'] = member_copy.pop('nested_members')
                        member_copy['expandable'] = True
                        if 'member_count' not in member_copy:
                            member_copy['member_count'] = len(member_copy['members'])

                    prefix_groups[prefix].append(member_copy)
                    prefix_found = True

        if not prefix_found:
            # No common prefix found, add as individual item
            # Preserve all original member properties
            member_copy = member.copy()
            member_copy.update({
                'display_name': f"{member_name} → {member_ip}"
            })

            # Convert nested_members to expandable format if present
            if member_copy.get('type') == 'group' and 'nested_members' in member_copy:
                member_copy['members'] = member_copy.pop('nested_members')
                member_copy['expandable'] = True
                if 'member_count' not in member_copy:
                    member_copy['member_count'] = len(member_copy['members'])

            ungrouped_members.append(member_copy)

    # Create hierarchical structure
    hierarchical_members = []

    # Add grouped members
    for prefix, members in prefix_groups.items():
        if len(members) > 1:  # Only group if there are multiple members
            hierarchical_members.append({
                'name': prefix,
                'ip': f"Group with {len(members)} members",
                'type': 'group',
                'display_name': f"{prefix} → Group with {len(members)} members",
                'members': members,
                'member_count': len(members),
                'expandable': True
            })
        else:
            # Single member, don't group
            ungrouped_members.extend(members)

    # Add ungrouped members
    hierarchical_members.extend(ungrouped_members)

    logger.debug(f"DEBUG: group_by_prefix_for_policy_display returning {len(hierarchical_members)} hierarchical members")
    if hierarchical_members:
        logger.debug(f"DEBUG: First few hierarchical members: {hierarchical_members[:3] if len(hierarchical_members) > 3 else hierarchical_members}")

    return hierarchical_members

def flatten_member_details_for_policy_display(member_details):
    """
    Recursively flatten member_details to show individual IP addresses for policy expansion.
    Converts nested group structures into individual IP address entries.
    """
    if not member_details:
        return []

    flattened_members = []

    for member in member_details:
        if not member or not isinstance(member, dict):
            continue

        member_type = member.get('type', 'unknown')
        member_name = member.get('name', '')
        member_ip = member.get('ip', '')

        if member_type == 'address':
            # Individual address object - add directly
            flattened_members.append({
                'name': member_name,
                'ip': member_ip,
                'type': 'address'
            })
        elif member_type == 'group' and member.get('nested_members'):
            # Nested group - recursively flatten its members
            nested_members = member.get('nested_members', [])
            flattened_nested = flatten_member_details_for_policy_display(nested_members)
            flattened_members.extend(flattened_nested)
        elif member_type == 'group':
            # Group without nested_members - try to resolve it directly
            group_name = member_name
            addr_group = FirewallAddressGroup.query.join(ConfigFile).filter(
                FirewallAddressGroup.name == group_name
            ).order_by(ConfigFile.upload_date.desc()).first()

            if addr_group and addr_group.member_details:
                try:
                    group_member_details = json.loads(addr_group.member_details)
                    flattened_nested = flatten_member_details_for_policy_display(group_member_details)
                    flattened_members.extend(flattened_nested)
                except Exception:
                    # If we can't parse, add as a single entry
                    flattened_members.append({
                        'name': member_name,
                        'ip': member_ip or f"Group: {member_name}",
                        'type': 'group'
                    })
            else:
                # Add as a single group entry if we can't resolve further
                flattened_members.append({
                    'name': member_name,
                    'ip': member_ip or f"Group: {member_name}",
                    'type': 'group'
                })
        else:
            # Missing or other types - add as is
            flattened_members.append({
                'name': member_name,
                'ip': member_ip,
                'type': member_type
            })

    return flattened_members

def search_firewall_objects(object_name, infrastructure_filter=None):
    """Search for object name in firewall configurations"""
    results = {
        'address_objects': [],
        'address_groups': [],
        'policies': [],
        'nat_policies': []
    }
    
    object_name = object_name.strip()

    # Get config file IDs filtered by infrastructure (only Firewall files)
    all_filtered_ids = get_infrastructure_config_file_ids(infrastructure_filter)

    # Filter to only include Firewall config files
    firewall_config_files = ConfigFile.query.filter(
        db.and_(
            ConfigFile.id.in_(all_filtered_ids),
            db.or_(
                ConfigFile.filename.like('%FW%'),  # Standard Firewall config files
                ConfigFile.filename.like('%ADMIN%')  # Management Firewall files
            )
        )
    ).all()

    firewall_config_file_ids = [cf.id for cf in firewall_config_files]

    # Search direct address object matches by name (no limit)
    direct_matches = FirewallAddressObject.query.filter(
        db.and_(
            FirewallAddressObject.name.ilike(f'%{object_name}%'),
            FirewallAddressObject.config_file_id.in_(firewall_config_file_ids)
        )
    ).all()
    
    results['address_objects'] = [obj.serialize for obj in direct_matches]
    matched_object_names = [obj.name for obj in direct_matches]  # All names for policy search
    
    # Search address groups by name and by members (no limit)
    address_groups = FirewallAddressGroup.query.filter(
        db.and_(
            db.or_(
                FirewallAddressGroup.name.ilike(f'%{object_name}%'),
                FirewallAddressGroup.members.ilike(f'%{object_name}%')
            ),
            FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids)
        )
    ).all()
    
    # Serialize all groups first, then filter out those without infrastructure mapping
    serialized_groups = [group.serialize for group in address_groups]
    # Filter out groups with "Unknown" environment (no infrastructure mapping)
    filtered_groups = [group for group in serialized_groups if group.get('environment', 'Unknown') != 'Unknown']

    results['address_groups'] = filtered_groups
    # Use only filtered groups for policy search to maintain consistency
    filtered_group_objects = [group for group in address_groups
                            if any(fg['id'] == group.id for fg in filtered_groups)]
    relevant_group_names = [group.name for group in filtered_group_objects]  # All names for policy search
    
    # Search policies containing the object names or groups using database queries instead of loading all
    matched_policies = []
    
    # Limit the number of names we search for to prevent timeout
    search_names = (matched_object_names + relevant_group_names)  # Search all names
    
    # If we have specific object/group names, search for policies containing them
    if search_names:
        for name in search_names:
            # Search policies where source_addresses or destination_addresses contain the name
            policies = FirewallPolicy.query.filter(
                db.and_(
                    db.or_(
                        FirewallPolicy.source_addresses.ilike(f'%{name}%'),
                        FirewallPolicy.destination_addresses.ilike(f'%{name}%')
                    ),
                    FirewallPolicy.config_file_id.in_(firewall_config_file_ids)
                )
            ).all()  # Remove arbitrary limit that cuts off valid results
            matched_policies.extend(policies)
            
            # Continue searching all policies for completeness
    
    # Also search directly for the object name in policy addresses (no limit)
    direct_policy_matches = FirewallPolicy.query.filter(
        db.and_(
            db.or_(
                FirewallPolicy.source_addresses.ilike(f'%{object_name}%'),
                FirewallPolicy.destination_addresses.ilike(f'%{object_name}%')
            ),
            FirewallPolicy.config_file_id.in_(firewall_config_file_ids)
        )
    ).all()  # Remove arbitrary limit that cuts off valid results
    
    matched_policies.extend(direct_policy_matches)
    
    # Remove duplicates based on policy ID (no limit)
    unique_policies = {}
    for policy in matched_policies:
        unique_policies[policy.id] = policy
    
    all_policies = list(unique_policies.values())
    
    for policy in all_policies:
        policy_matches = False
        match_details = {'source': [], 'destination': []}
        
        # Check source addresses
        if policy.source_addresses:
            try:
                sources = json.loads(policy.source_addresses) if isinstance(policy.source_addresses, str) else policy.source_addresses
                for src in sources:
                    # Use more precise matching - split by underscore to find exact component matches
                    name_lower = object_name.lower()
                    src_lower = src.lower()
                    
                    # Split both strings by underscore to find exact component matches
                    name_components = name_lower.split('_')
                    src_components = src_lower.split('_')
                    
                    # Check if the search term matches any component exactly or as a complete sequence
                    if len(name_components) == 1:
                        # Single component search - must match a complete component
                        exact_or_boundary_match = name_lower in src_components
                    else:
                        # Multi-component search - check if the sequence appears in src_components
                        name_len = len(name_components)
                        exact_or_boundary_match = False
                        for i in range(len(src_components) - name_len + 1):
                            if src_components[i:i+name_len] == name_components:
                                exact_or_boundary_match = True
                                break
                    
                    if (exact_or_boundary_match or 
                        src in matched_object_names or 
                        src in relevant_group_names):
                        policy_matches = True
                        match_details['source'].append(src)
            except Exception:
                pass
        
        # Check destination addresses  
        if policy.destination_addresses:
            try:
                destinations = json.loads(policy.destination_addresses) if isinstance(policy.destination_addresses, str) else policy.destination_addresses
                for dst in destinations:
                    # Use more precise matching - split by underscore to find exact component matches
                    name_lower = object_name.lower()
                    dst_lower = dst.lower()
                    
                    # Split both strings by underscore to find exact component matches
                    name_components = name_lower.split('_')
                    dst_components = dst_lower.split('_')
                    
                    # Check if the search term matches any component exactly or as a complete sequence
                    if len(name_components) == 1:
                        # Single component search - must match a complete component
                        exact_or_boundary_match = name_lower in dst_components
                    else:
                        # Multi-component search - check if the sequence appears in dst_components
                        name_len = len(name_components)
                        exact_or_boundary_match = False
                        for i in range(len(dst_components) - name_len + 1):
                            if dst_components[i:i+name_len] == name_components:
                                exact_or_boundary_match = True
                                break
                    
                    if (exact_or_boundary_match or 
                        dst in matched_object_names or 
                        dst in relevant_group_names):
                        policy_matches = True
                        match_details['destination'].append(dst)
            except Exception:
                pass
        
        if policy_matches:
            policy_data = policy.serialize
            policy_data['match_details'] = match_details
            
            # Add IP address mappings for all address objects in this policy
            address_object_mappings = {}
            
            # Get all unique address object names from source and destination
            all_address_names = set()
            try:
                if policy.source_addresses:
                    sources = json.loads(policy.source_addresses) if isinstance(policy.source_addresses, str) else policy.source_addresses
                    all_address_names.update(sources)
            except Exception:
                pass
            
            try:
                if policy.destination_addresses:
                    destinations = json.loads(policy.destination_addresses) if isinstance(policy.destination_addresses, str) else policy.destination_addresses
                    all_address_names.update(destinations)
            except Exception:
                pass
            
            # Look up IP addresses for each address object name
            for addr_name in all_address_names:
                # Skip if it's already an IP address
                try:
                    ipaddress.ip_address(addr_name)
                    continue  # It's already an IP address
                except Exception:
                    pass
                
                # Look up the address object
                addr_obj = FirewallAddressObject.query.filter_by(
                    name=addr_name,
                    config_file_id=policy.config_file_id
                ).first()
                if addr_obj:
                    address_object_mappings[addr_name] = {
                        'ip_address': addr_obj.ip_address,
                        'cidr_notation': addr_obj.cidr_notation,
                        'object_type': addr_obj.object_type
                    }
                else:
                    # Could be an address group - use group from SAME config file as policy
                    addr_group = FirewallAddressGroup.query.filter_by(
                        name=addr_name,
                        config_file_id=policy.config_file_id
                    ).first()
                    if addr_group:
                        try:
                            # Use pre-computed resolved members if available
                            if addr_group.resolved_members:
                                resolved_ips = json.loads(addr_group.resolved_members)
                                member_count = addr_group.member_count or len(resolved_ips)

                                # Show group name with member count instead of all IPs
                                group_display = f"{addr_name} ({member_count} members)"

                                # Get detailed member information and flatten for policy display
                                member_details = None
                                hierarchical_members = None
                                if addr_group.member_details:
                                    try:
                                        raw_member_details = json.loads(addr_group.member_details)
                                        # Flatten nested groups to show individual IP addresses
                                        member_details = flatten_member_details_for_policy_display(raw_member_details)
                                        # Use natural config hierarchy only - no artificial grouping
                                        hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                    except Exception:
                                        member_details = None
                                        hierarchical_members = None

                                address_object_mappings[addr_name] = {
                                    'ip_address': group_display,
                                    'cidr_notation': None,
                                    'object_type': 'group',
                                    'member_count': member_count,
                                    'member_details': member_details,
                                    'hierarchical_members': hierarchical_members
                                }
                            else:
                                # Fallback to simple method for groups without pre-computed members
                                members = json.loads(addr_group.members) if isinstance(addr_group.members, str) else addr_group.members
                                member_ips = []
                                for member in members:  # No limit for accuracy
                                    member_obj = FirewallAddressObject.query.filter_by(name=member).first()
                                    if member_obj and member_obj.ip_address:
                                        member_ips.append(member_obj.ip_address)
                                address_object_mappings[addr_name] = {
                                    'ip_address': f"{addr_name} ({len(member_ips)} members)" if member_ips else 'Unknown Group',
                                    'cidr_notation': None,
                                    'object_type': 'group',
                                    'member_count': len(member_ips),
                                    'member_details': None,
                                    'hierarchical_members': None
                                }
                        except Exception:
                            address_object_mappings[addr_name] = {
                                'ip_address': 'Unknown Group',
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_details': None,
                                'hierarchical_members': None
                            }
                    else:
                        # Could be a VIP group - use VIP group from SAME config file as policy
                        vip_group = FirewallVipGroup.query.filter_by(
                            name=addr_name,
                            config_file_id=policy.config_file_id
                        ).first()
                        if vip_group:
                            try:
                                # Use pre-computed resolved members if available
                                if vip_group.resolved_members:
                                    resolved_ips = json.loads(vip_group.resolved_members)
                                    member_count = vip_group.member_count or len(resolved_ips)

                                    # Show VIP group name with member count
                                    group_display = f"{addr_name} ({member_count} VIPs)"

                                    # Get detailed member information
                                    member_details = None
                                    hierarchical_members = None
                                    if vip_group.member_details:
                                        try:
                                            raw_member_details = json.loads(vip_group.member_details)
                                            # Flatten for policy display
                                            member_details = flatten_member_details_for_policy_display(raw_member_details)
                                            # Preserve hierarchy
                                            hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                        except Exception:
                                            member_details = None
                                            hierarchical_members = None

                                    address_object_mappings[addr_name] = {
                                        'ip_address': group_display,
                                        'cidr_notation': None,
                                        'object_type': 'vip_group',
                                        'member_count': member_count,
                                        'member_details': member_details,
                                        'hierarchical_members': hierarchical_members
                                    }
                                else:
                                    # Fallback
                                    address_object_mappings[addr_name] = {
                                        'ip_address': f"{addr_name} (VIP Group)",
                                        'cidr_notation': None,
                                        'object_type': 'vip_group',
                                        'member_count': 0,
                                        'member_details': None,
                                        'hierarchical_members': None
                                    }
                            except Exception:
                                address_object_mappings[addr_name] = {
                                    'ip_address': 'Unknown VIP Group',
                                    'cidr_notation': None,
                                    'object_type': 'vip_group',
                                    'member_details': None,
                                    'hierarchical_members': None
                                }

            policy_data['address_mappings'] = address_object_mappings
            results['policies'].append(policy_data)
    
    # Search NAT policies containing the object names or groups
    try:
        # Use dict to track unique NAT policies by environment and policy identity
        # Key: (environment, policy_id, name, source_zone, dest_zone), Value: latest nat_policy
        unique_nat_policies = {}
        
        # Search by object name in source/destination addresses (includes original object_name)
        search_names = matched_object_names + relevant_group_names + [object_name]
        
        for name in search_names:
            nat_policies = FirewallNatPolicy.query.filter(
                db.and_(
                    db.or_(
                        FirewallNatPolicy.source_addresses.ilike(f'%{name}%'),
                        FirewallNatPolicy.destination_addresses.ilike(f'%{name}%'),
                        FirewallNatPolicy.source_translation.ilike(f'%{name}%'),
                        FirewallNatPolicy.destination_translation.ilike(f'%{name}%'),
                        FirewallNatPolicy.name.ilike(f'%{name}%')
                    ),
                    FirewallNatPolicy.config_file_id.in_(firewall_config_file_ids)
                )
            ).all()  # Remove arbitrary limit that cuts off valid results
            
            # Deduplicate NAT policies by environment and policy identity
            for nat_policy in nat_policies:
                # Get environment name from config file
                env_name = "Unknown"
                if nat_policy.config_file:
                    filename = nat_policy.config_file.filename
                    if 'UAT-FW01' in filename:
                        env_name = "UAT FW"
                    elif 'BRAVO-FW01' in filename:
                        env_name = "Bravo FW"
                    elif 'ALPHA-FW01' in filename:
                        env_name = "Alpha FW"
                    elif 'CHARLIE-FW01' in filename:
                        env_name = "Charlie FW"
                    elif 'LoadTest-FW01' in filename:
                        env_name = "LoadTest FW"
                    elif 'DELTA-FW01' in filename:
                        env_name = "UAT FW"
                    elif 'DELTA-ADMIN-FW01' in filename:
                        env_name = "Admin FW"
                    elif 'ADMIN-FW01' in filename:
                        env_name = "Admin FW"
                
                # Create unique key based on environment and policy identity
                policy_key = (
                    env_name,
                    nat_policy.policy_id,
                    nat_policy.name,
                    nat_policy.source_zone,
                    nat_policy.destination_zone
                )
                
                # Keep only the most recent version (highest config file ID)
                if policy_key not in unique_nat_policies:
                    unique_nat_policies[policy_key] = nat_policy
                else:
                    existing_policy = unique_nat_policies[policy_key]
                    if nat_policy.config_file_id > existing_policy.config_file_id:
                        unique_nat_policies[policy_key] = nat_policy
        
        # Convert deduplicated policies back to list
        nat_policy_matches = list(unique_nat_policies.values())  # No limit
        
        # No need for separate direct search since object_name is included above
        # Also no need for additional deduplication since we already deduplicated during search
        final_nat_policies = nat_policy_matches
        
        for nat_policy in final_nat_policies:
            nat_policy_data = nat_policy.serialize
            
            # Add match details
            match_details = {'source': [], 'destination': [], 'source_translation': [], 'destination_translation': []}
            
            # Check which addresses matched
            try:
                if nat_policy.source_addresses:
                    sources = json.loads(nat_policy.source_addresses) if isinstance(nat_policy.source_addresses, str) else nat_policy.source_addresses
                    for src in sources:
                        # Use more precise matching - split by underscore to find exact component matches
                        name_lower = object_name.lower()
                        src_lower = src.lower()
                        
                        # Split both strings by underscore to find exact component matches
                        name_components = name_lower.split('_')
                        src_components = src_lower.split('_')
                        
                        # Check if the search term matches any component exactly or as a complete sequence
                        if len(name_components) == 1:
                            # Single component search - must match a complete component
                            exact_or_boundary_match = name_lower in src_components
                        else:
                            # Multi-component search - check if the sequence appears in src_components
                            name_len = len(name_components)
                            exact_or_boundary_match = False
                            for i in range(len(src_components) - name_len + 1):
                                if src_components[i:i+name_len] == name_components:
                                    exact_or_boundary_match = True
                                    break
                        
                        if (exact_or_boundary_match or 
                            src in matched_object_names or 
                            src in relevant_group_names):
                            match_details['source'].append(src)
            except Exception:
                pass
            
            try:
                if nat_policy.destination_addresses:
                    destinations = json.loads(nat_policy.destination_addresses) if isinstance(nat_policy.destination_addresses, str) else nat_policy.destination_addresses
                    for dst in destinations:
                        # Use more precise matching - split by underscore to find exact component matches
                        name_lower = object_name.lower()
                        dst_lower = dst.lower()
                        
                        # Split both strings by underscore to find exact component matches
                        name_components = name_lower.split('_')
                        dst_components = dst_lower.split('_')
                        
                        # Check if the search term matches any component exactly or as a complete sequence
                        if len(name_components) == 1:
                            # Single component search - must match a complete component
                            exact_or_boundary_match = name_lower in dst_components
                        else:
                            # Multi-component search - check if the sequence appears in dst_components
                            name_len = len(name_components)
                            exact_or_boundary_match = False
                            for i in range(len(dst_components) - name_len + 1):
                                if dst_components[i:i+name_len] == name_components:
                                    exact_or_boundary_match = True
                                    break
                        
                        if (exact_or_boundary_match or 
                            dst in matched_object_names or 
                            dst in relevant_group_names):
                            match_details['destination'].append(dst)
            except Exception:
                pass
            
            # Check translation addresses
            try:
                if nat_policy.source_translation:
                    if object_name.lower() in str(nat_policy.source_translation).lower():
                        match_details['source_translation'].append(str(nat_policy.source_translation))
            except Exception:
                pass
                
            try:
                if nat_policy.destination_translation:
                    if object_name.lower() in str(nat_policy.destination_translation).lower():
                        match_details['destination_translation'].append(str(nat_policy.destination_translation))
            except Exception:
                pass
            
            nat_policy_data['match_details'] = match_details
            
            # Add address mappings (similar to regular policies)
            address_object_mappings = {}
            all_address_names = set()
            
            try:
                if nat_policy.source_addresses:
                    sources = json.loads(nat_policy.source_addresses) if isinstance(nat_policy.source_addresses, str) else nat_policy.source_addresses
                    all_address_names.update(sources)
            except Exception:
                pass
                
            try:
                if nat_policy.destination_addresses:
                    destinations = json.loads(nat_policy.destination_addresses) if isinstance(nat_policy.destination_addresses, str) else nat_policy.destination_addresses
                    all_address_names.update(destinations)
            except Exception:
                pass
            
            # Look up IP addresses for each address object name
            for addr_name in all_address_names:
                # Skip if it's already an IP address
                try:
                    ipaddress.ip_address(addr_name)
                    continue
                except Exception:
                    pass
                
                # Look up the address object
                addr_obj = FirewallAddressObject.query.filter_by(
                    name=addr_name,
                    config_file_id=policy.config_file_id
                ).first()
                if addr_obj:
                    address_object_mappings[addr_name] = {
                        'ip_address': addr_obj.ip_address,
                        'cidr_notation': addr_obj.cidr_notation,
                        'object_type': addr_obj.object_type
                    }
                else:
                    # Could be an address group - use group from SAME config file as policy
                    addr_group = FirewallAddressGroup.query.filter_by(
                        name=addr_name,
                        config_file_id=policy.config_file_id
                    ).first()
                    if addr_group:
                        try:
                            # Use pre-computed resolved members if available
                            if addr_group.resolved_members:
                                resolved_ips = json.loads(addr_group.resolved_members)
                                member_count = addr_group.member_count or len(resolved_ips)

                                # Show group name with member count instead of all IPs
                                group_display = f"{addr_name} ({member_count} members)"

                                # Get detailed member information and flatten for policy display
                                member_details = None
                                hierarchical_members = None
                                if addr_group.member_details:
                                    try:
                                        raw_member_details = json.loads(addr_group.member_details)
                                        # Flatten nested groups to show individual IP addresses
                                        member_details = flatten_member_details_for_policy_display(raw_member_details)
                                        # Use natural config hierarchy only - no artificial grouping
                                        hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                    except Exception:
                                        member_details = None
                                        hierarchical_members = None

                                address_object_mappings[addr_name] = {
                                    'ip_address': group_display,
                                    'cidr_notation': None,
                                    'object_type': 'group',
                                    'member_count': member_count,
                                    'member_details': member_details,
                                    'hierarchical_members': hierarchical_members
                                }
                            else:
                                # Fallback to old method for groups without pre-computed members
                                members = json.loads(addr_group.members) if isinstance(addr_group.members, str) else addr_group.members
                                member_ips = []
                                for member in members:  # Process all members
                                    member_obj = FirewallAddressObject.query.filter_by(name=member).first()
                                    if member_obj and member_obj.ip_address:
                                        member_ips.append(member_obj.ip_address)
                                address_object_mappings[addr_name] = {
                                    'ip_address': f"{addr_name} ({len(member_ips)} members)" if member_ips else 'Unknown Group',
                                    'cidr_notation': None,
                                    'object_type': 'group',
                                    'member_count': len(member_ips),
                                    'member_details': None,
                                    'hierarchical_members': None
                                }
                        except Exception:
                            address_object_mappings[addr_name] = {
                                'ip_address': 'Unknown Group',
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_count': 0,
                                'member_details': None,
                                'hierarchical_members': None
                            }
                    else:
                        # Could be a VIP group - use VIP group from SAME config file as NAT policy
                        vip_group = FirewallVipGroup.query.filter_by(
                            name=addr_name,
                            config_file_id=nat_policy.config_file_id
                        ).first()
                        if vip_group:
                            try:
                                if vip_group.resolved_members:
                                    resolved_ips = json.loads(vip_group.resolved_members)
                                    member_count = vip_group.member_count or len(resolved_ips)
                                    group_display = f"{addr_name} ({member_count} VIPs)"

                                    member_details = None
                                    hierarchical_members = None
                                    if vip_group.member_details:
                                        try:
                                            raw_member_details = json.loads(vip_group.member_details)
                                            member_details = flatten_member_details_for_policy_display(raw_member_details)
                                            hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                        except Exception:
                                            member_details = None
                                            hierarchical_members = None

                                    address_object_mappings[addr_name] = {
                                        'ip_address': group_display,
                                        'cidr_notation': None,
                                        'object_type': 'vip_group',
                                        'member_count': member_count,
                                        'member_details': member_details,
                                        'hierarchical_members': hierarchical_members
                                    }
                                else:
                                    address_object_mappings[addr_name] = {
                                        'ip_address': f"{addr_name} (VIP Group)",
                                        'cidr_notation': None,
                                        'object_type': 'vip_group',
                                        'member_count': 0,
                                        'member_details': None,
                                        'hierarchical_members': None
                                    }
                            except Exception:
                                address_object_mappings[addr_name] = {
                                    'ip_address': 'Unknown VIP Group',
                                    'cidr_notation': None,
                                    'object_type': 'vip_group',
                                    'member_details': None,
                                    'hierarchical_members': None
                                }

            nat_policy_data['address_mappings'] = address_object_mappings
            results['nat_policies'].append(nat_policy_data)
            
    except Exception as e:
        # Handle case where NAT policies table doesn't exist or is empty
        logger.warning(f"NAT policies search error: {e}")
        pass
    
    return results

def search_ltm_objects(object_name, infrastructure_filter=None):
    """Search for object name in LTM configurations"""
    # Get only the most recent config file for each filename (same logic as IP search)
    # ConfigFile already imported at top
    from sqlalchemy import func, desc
    
    # Get config file IDs filtered by infrastructure (only LTM/SLB files)
    all_filtered_ids = get_infrastructure_config_file_ids(infrastructure_filter)

    # Filter to only include LTM/SLB config files
    ltm_config_files = ConfigFile.query.filter(
        db.and_(
            ConfigFile.id.in_(all_filtered_ids),
            db.or_(
                ConfigFile.filename.like('%LTM%'),  # Standard LTM config files
                ConfigFile.filename.like('H2SLB01%'),  # H2SLB01.TRZ.PRD LTM system (legacy)
                ConfigFile.filename.like('%SLB%')   # Other SLB (Server Load Balancer) systems
            )
        )
    ).all()

    latest_config_file_ids = [cf.id for cf in ltm_config_files]
    
    unique_virtual_servers = {}
    object_name = object_name.strip()
    
    # Search in virtual servers by name (no limit) - only latest config files
    vs_matches = LtmVirtualServer.query.filter(
        db.and_(
            LtmVirtualServer.name.ilike(f'%{object_name}%'),
            LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
        )
    ).all()
    
    # Add direct VS matches
    for vs in vs_matches:
        vs_data = vs.serialize
        vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
        
        # Get all nodes for this VS's pool (using same logic as IP search)
        pool_nodes = []
        unique_nodes = {}  # Use dict to deduplicate nodes by ip:port
        
        # Try multiple approaches to find pool nodes, similar to IP search logic
        pools = []
        if vs.pool_name:
            # Approach 1: Direct pool name match
            pools = LtmPool.query.filter(
                db.and_(
                    LtmPool.name == vs.pool_name,
                    LtmPool.config_file_id.in_(latest_config_file_ids)
                )
            ).all()
            
        # Approach 2: If no pools found, try pattern matching based on VS name  
        if not pools:
            vs_name_clean = vs.name.replace('/Common/', '')
            
            # Try different pool naming patterns
            pool_patterns = []
            if vs_name_clean.startswith('vs'):
                # vs28000_TapTap_MEM -> po28000_TapTap_MEM
                base_pattern = vs_name_clean.replace('vs', 'po', 1)
                pool_patterns.append(base_pattern)
                pool_patterns.append(f'/Common/{base_pattern}')
                
                # Also try without port suffix for _443 and _Cloud variants
                if '_443' in vs_name_clean or '_Cloud' in vs_name_clean:
                    # vs28000_TapTap_MEM_443 -> try po28000_TapTap_MEM (without _443)
                    base_name = vs_name_clean.replace('_443', '').replace('_Cloud', '')
                    base_pool = base_name.replace('vs', 'po', 1)
                    pool_patterns.append(base_pool)
                    pool_patterns.append(f'/Common/{base_pool}')
                    
            if vs_name_clean.startswith('u-vs'):
                # u-vs28000_TapTap_MEM -> u-po28000_TapTap_MEM  
                base_pattern = vs_name_clean.replace('u-vs', 'u-po', 1)
                pool_patterns.append(base_pattern)
                pool_patterns.append(f'/Common/{base_pattern}')
                
                # Also try without port suffix for _443 and _Cloud variants
                if '_443' in vs_name_clean or '_Cloud' in vs_name_clean:
                    base_name = vs_name_clean.replace('_443', '').replace('_Cloud', '')
                    base_pool = base_name.replace('u-vs', 'u-po', 1)
                    pool_patterns.append(base_pool)
                    pool_patterns.append(f'/Common/{base_pool}')
                
            # Search for pools matching these patterns
            for pattern in pool_patterns:
                pattern_pools = LtmPool.query.filter(
                    db.and_(
                        LtmPool.name == pattern,
                        LtmPool.config_file_id.in_(latest_config_file_ids)
                    )
                ).all()
                pools.extend(pattern_pools)
                
        # Approach 3: If still no pools, try reverse lookup - find nodes that reference this VS
        # by looking for nodes whose pools might be associated with this VS
        if not pools:
            # This is similar to how the IP search works - find nodes first, then trace back to VS
            all_pools = LtmPool.query.filter(
                LtmPool.config_file_id.in_(latest_config_file_ids)
            ).all()
            
            for pool in all_pools:
                # Check if this pool might be associated with our VS
                pool_name_clean = pool.name.replace('/Common/', '')
                vs_name_clean = vs.name.replace('/Common/', '')
                
                # Check various name patterns
                potential_vs_names = []
                if pool_name_clean.startswith('po'):
                    potential_vs_names.append(pool_name_clean.replace('po', 'vs', 1))
                    potential_vs_names.append(f'/Common/{pool_name_clean.replace("po", "vs", 1)}')
                if pool_name_clean.startswith('u-po'):
                    potential_vs_names.append(pool_name_clean.replace('u-po', 'u-vs', 1))
                    potential_vs_names.append(f'/Common/{pool_name_clean.replace("u-po", "u-vs", 1)}')
                    
                if vs.name in potential_vs_names or vs_name_clean in [name.replace('/Common/', '') for name in potential_vs_names]:
                    pools.append(pool)
            
        # Now get nodes from all found pools
        for pool in pools:
            nodes = LtmNode.query.filter(
                db.and_(
                    LtmNode.pool_id == pool.id,
                    LtmNode.config_file_id.in_(latest_config_file_ids)
                )
            ).all()
            for node in nodes:
                node_key = f"{node.ip_address}:{node.port}"
                if node_key not in unique_nodes:
                    unique_nodes[node_key] = node.serialize

        pool_nodes = list(unique_nodes.values())

        # If we found pools and pool nodes, ensure the pool name is set in vs_data
        if pools and pool_nodes:
            # Use the first pool found (they should all have the same name for a given VS)
            vs_data['pool_name'] = pools[0].name
        
        unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
        unique_virtual_servers[unique_key] = {
            'virtual_server': vs_data,
            'pool_nodes': pool_nodes
        }
        
        # Continue processing all results
    
    # Search in pools by name (no limit) - only latest config files
    pool_matches = LtmPool.query.filter(
        db.and_(
            LtmPool.name.ilike(f'%{object_name}%'),
            LtmPool.config_file_id.in_(latest_config_file_ids)
        )
    ).all()
    
    for pool in pool_matches:
        # Continue processing all results
            
        # Find virtual servers using this pool (limit to 20) - only latest config files
        virtual_servers = LtmVirtualServer.query.filter(
            db.and_(
                LtmVirtualServer.pool_name == pool.name,
                LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
            )
        ).all()
        
        for vs in virtual_servers:
            unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
            if unique_key not in unique_virtual_servers:
                vs_data = vs.serialize
                vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
                # Ensure pool name is set correctly
                vs_data['pool_name'] = pool.name
                
                # Get all nodes for this pool - only from latest config files
                nodes = LtmNode.query.filter(
                    db.and_(
                        LtmNode.pool_id == pool.id,
                        LtmNode.config_file_id.in_(latest_config_file_ids)
                    )
                ).all()
                pool_nodes = [node_obj.serialize for node_obj in nodes]
                
                unique_virtual_servers[unique_key] = {
                    'virtual_server': vs_data,
                    'pool_nodes': pool_nodes
                }
                
                # Stop if we have too many results
                if len(unique_virtual_servers) >= 50:
                    break
    
    results = {
        'virtual_servers': list(unique_virtual_servers.values()),
        'pools_and_nodes': []
    }
    
    return results

def search_firewall_configs(ip_address, search_direction='both', page=1, page_size=1000, infrastructure_filter=None):
    """Search for IP address in firewall configurations with pagination"""
    results = {
        'address_objects': [],
        'policies': [],
        'nat_policies': [],
        'pagination': {
            'current_page': page,
            'page_size': page_size,
            'total_policies': 0,
            'total_nat_policies': 0,
            'has_more_policies': False,
            'has_more_nat_policies': False
        }
    }

    # Get config file IDs filtered by infrastructure (only Firewall files)
    all_filtered_ids = get_infrastructure_config_file_ids(infrastructure_filter)

    # Filter to only include Firewall config files
    firewall_config_files = ConfigFile.query.filter(
        db.and_(
            ConfigFile.id.in_(all_filtered_ids),
            db.or_(
                ConfigFile.filename.like('%FW%'),  # Standard Firewall config files
                ConfigFile.filename.like('%ADMIN%')  # Management Firewall files
            )
        )
    ).all()

    firewall_config_file_ids = [cf.id for cf in firewall_config_files]

    # Search direct address object matches (support partial IPs)
    ip_conditions = build_partial_ip_conditions(ip_address, FirewallAddressObject.ip_address)
    direct_matches = FirewallAddressObject.query.filter(
        db.and_(
            db.or_(*ip_conditions),
            FirewallAddressObject.config_file_id.in_(firewall_config_file_ids)
        )
    ).all()
    
    # Also search CIDR notation for partial matches
    if is_partial_ip(ip_address):
        cidr_matches = FirewallAddressObject.query.filter(
            db.and_(
                FirewallAddressObject.cidr_notation.like(f"{ip_address}.%"),
                FirewallAddressObject.config_file_id.in_(firewall_config_file_ids)
            )
        ).all()
        direct_matches.extend(cidr_matches)

    # Search for subnet matches using more efficient database queries
    subnet_matches = []

    # Use a more targeted approach for subnet matching instead of loading all objects
    # For a specific IP like 203.0.113.81, search for subnet patterns in the same /24 range
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        # Extract the first 3 octets to search all subnets in the same /24 range
        ip_parts = str(ip_obj).split('.')
        if len(ip_parts) >= 3:
            # Search for all subnets in the same /24 range (e.g., 203.0.113.x)
            # This catches /25, /26, /27, /28, /29, /30, /31, /32 subnets
            subnet_objects = FirewallAddressObject.query.filter(
                db.and_(
                    FirewallAddressObject.config_file_id.in_(firewall_config_file_ids),
                    FirewallAddressObject.object_type == 'subnet',
                    db.or_(
                        # Same /24 range (most common - /25 through /32)
                        FirewallAddressObject.cidr_notation.like(f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.%"),
                        # Larger /16 subnet
                        FirewallAddressObject.cidr_notation.like(f"{ip_parts[0]}.{ip_parts[1]}.0.0/%"),
                        # Larger /8 subnet
                        FirewallAddressObject.cidr_notation.like(f"{ip_parts[0]}.0.0.0/%")
                    )
                )
            ).all()

            # Check each subnet to see if our target IP is in it
            for obj in subnet_objects:
                if obj.cidr_notation and obj.ip_address != ip_address:
                    if is_ip_in_subnet(ip_address, obj.cidr_notation):
                        subnet_matches.append(obj)
    except ValueError:
        # If not a valid IP, skip subnet matching
        pass
    
    # Remove duplicates by creating a set of unique objects based on name and IP
    unique_objects = {}
    for obj in direct_matches + subnet_matches:
        # Use name and ip_address as the unique key to avoid duplicates
        key = f"{obj.name}_{obj.ip_address}_{obj.cidr_notation}"
        unique_objects[key] = obj
    
    matched_objects = list(unique_objects.values())
    
    # Sort address objects by CIDR prefix (from /32 to /24 to /16 etc)
    def get_cidr_prefix(obj):
        """Extract CIDR prefix for sorting. Higher numbers (/32) come first."""
        if obj.cidr_notation:
            try:
                # Extract the prefix number from CIDR notation like '192.0.2.1/32'
                return int(obj.cidr_notation.split('/')[-1])
            except Exception:
                return 0  # Default for invalid CIDR
        elif obj.ip_address:
            # If no CIDR notation, assume /32 for individual IPs
            try:
                ipaddress.ip_address(obj.ip_address)
                return 32  # Individual IP address
            except Exception:
                return 0  # Invalid IP
        return 0  # Default fallback
    
    # Sort by CIDR prefix descending (32, 24, 16, etc.)
    matched_objects.sort(key=get_cidr_prefix, reverse=True)
    
    results['address_objects'] = [obj.serialize for obj in matched_objects]

    # Find address groups containing these objects (including nested groups)
    matched_object_names = [obj.name for obj in matched_objects]

    # Find address groups that contain our IP using more efficient database queries
    relevant_groups = []

    # Search for groups containing our matched object names using database queries
    if matched_object_names:
        # Use LIKE queries to find groups that contain our matched objects
        group_conditions = []
        for obj_name in matched_object_names:
            group_conditions.append(FirewallAddressGroup.members.like(f'%"{obj_name}"%'))

        if group_conditions:
            matched_groups = FirewallAddressGroup.query.filter(
                db.and_(
                    FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids),
                    db.or_(*group_conditions)
                )
            ).all()

            for group in matched_groups:
                group_data = group.serialize
                group_data['object_type'] = 'group'
                relevant_groups.append(group_data)

    # Also search for groups that directly contain our IP in resolved_members
    # SQL pre-filtering (may include false positives - validated below)
    ip_groups_prefiltered = FirewallAddressGroup.query.filter(
        db.and_(
            FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids),
            FirewallAddressGroup.resolved_members.like(f'%{ip_address}%')
        )
    ).all()

    # Python validation: filter out false positives using proper IP/CIDR matching
    ip_groups = []
    for group in ip_groups_prefiltered:
        if group.resolved_members:
            try:
                resolved_ips = json.loads(group.resolved_members)
                # Check if IP is actually in this group using proper matching
                if any(is_ip_in_cidr_or_exact(ip_address, resolved_ip)
                       for resolved_ip in resolved_ips):
                    ip_groups.append(group)
            except (json.JSONDecodeError, TypeError):
                # Skip groups with invalid JSON data
                pass

    for group in ip_groups:
        # Avoid duplicates
        if not any(g['name'] == group.name for g in relevant_groups):
            group_data = group.serialize
            group_data['object_type'] = 'group'
            relevant_groups.append(group_data)

    # Add address groups to the address_objects results
    results['address_objects'].extend(relevant_groups)

    # Load all groups for policy processing (but more efficiently)
    all_groups = FirewallAddressGroup.query.filter(
        FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids)
    ).all()

    # Build search terms first to optimize policy queries
    # Include IP, matched object names, and relevant group names
    search_terms = set()
    search_terms.add(ip_address)
    search_terms.update(matched_object_names)

    # Add relevant group names from groups that contain our IP
    relevant_group_names = [group['name'] for group in relevant_groups]
    search_terms.update(relevant_group_names)

    # Load policies more efficiently using targeted searches
    # Instead of loading all policies, search for ones containing our terms
    all_policies = []

    # Split search into batches to avoid very large queries
    search_terms_list = list(search_terms)
    batch_size = 20

    for i in range(0, len(search_terms_list), batch_size):
        batch_terms = search_terms_list[i:i+batch_size]

        # Build OR conditions for source and destination addresses
        policy_conditions = []
        for term in batch_terms:
            # Search in source addresses
            policy_conditions.append(FirewallPolicy.source_addresses.like(f'%"{term}"%'))
            # Search in destination addresses
            policy_conditions.append(FirewallPolicy.destination_addresses.like(f'%"{term}"%'))

        if policy_conditions:
            batch_policies = FirewallPolicy.query.filter(
                db.and_(
                    FirewallPolicy.config_file_id.in_(firewall_config_file_ids),
                    db.or_(*policy_conditions)
                )
            ).all()
            all_policies.extend(batch_policies)

    # Remove duplicates
    unique_policies = {policy.id: policy for policy in all_policies}
    all_policies = list(unique_policies.values())

    # Organize groups by config file ID for fast lookup (reuse all_groups from above)
    groups_by_config_file = {}
    for group in all_groups:
        if group.config_file_id not in groups_by_config_file:
            groups_by_config_file[group.config_file_id] = []
        groups_by_config_file[group.config_file_id].append(group)

    # Build base search terms (IP and direct object matches)
    base_search_terms = set()
    base_search_terms.add(ip_address)
    base_search_terms.update(matched_object_names)

    # Build a global set of group names that contain our matched objects across ALL selected infrastructures
    # This ensures cross-config group resolution when the same group name exists in multiple configs
    global_group_names_with_matches = set()
    for group in all_groups:
        if group.members:
            try:
                # Parse the actual JSON members list
                members = json.loads(group.members) if isinstance(group.members, str) else group.members
                # Check for exact member name matches (not substring)
                if any(member_name in matched_object_names for member_name in members):
                    global_group_names_with_matches.add(group.name)
            except (json.JSONDecodeError, TypeError):
                # Skip groups with invalid member data
                continue

    # Filter policies by doing exact JSON member matching
    matching_policies = []
    for policy in all_policies:
        policy_matches = False
        match_details = {'source': [], 'destination': []}

        # Use global group names that contain our matched objects
        # This allows cross-config group resolution (e.g., ext_Office_Global in Delta will match policies in Charlie)
        policy_specific_search_terms = base_search_terms.copy()
        policy_specific_search_terms.update(global_group_names_with_matches)

        # Check source addresses (only if search_direction allows it)
        if search_direction in ['both', 'source'] and policy.source_addresses:
            try:
                sources = json.loads(policy.source_addresses) if isinstance(policy.source_addresses, str) else policy.source_addresses
                for src in sources:
                    # Check for exact match in our policy-specific search terms
                    if src in policy_specific_search_terms:
                        policy_matches = True
                        match_details['source'].append(src)
                        break  # Found a match, no need to check other sources
            except (json.JSONDecodeError, TypeError):
                pass

        # Check destination addresses (only if search_direction allows it)
        if search_direction in ['both', 'destination'] and policy.destination_addresses:
            try:
                destinations = json.loads(policy.destination_addresses) if isinstance(policy.destination_addresses, str) else policy.destination_addresses
                for dst in destinations:
                    # Check for exact match in our policy-specific search terms
                    if dst in policy_specific_search_terms:
                        policy_matches = True
                        match_details['destination'].append(dst)
                        break  # Found a match, no need to check other destinations
            except (json.JSONDecodeError, TypeError):
                pass

        if policy_matches:
            policy_data = policy.serialize
            policy_data['match_details'] = match_details
            matching_policies.append(policy_data)

    # Apply pagination to the filtered results
    total_policies = len(matching_policies)
    offset = (page - 1) * page_size
    paginated_policies = matching_policies[offset:offset + page_size]

    results['pagination']['total_policies'] = total_policies
    results['pagination']['has_more_policies'] = offset + page_size < total_policies

    # Add address object mappings to each policy result
    for policy_data in paginated_policies:
        # Add IP address mappings for all address objects in this policy
        address_object_mappings = {}

        # Get all unique address object names from source and destination
        all_address_names = set()
        if 'source_addresses' in policy_data and policy_data['source_addresses']:
            try:
                sources = json.loads(policy_data['source_addresses']) if isinstance(policy_data['source_addresses'], str) else policy_data['source_addresses']
                all_address_names.update(sources)
            except Exception:
                pass

        if 'destination_addresses' in policy_data and policy_data['destination_addresses']:
            try:
                destinations = json.loads(policy_data['destination_addresses']) if isinstance(policy_data['destination_addresses'], str) else policy_data['destination_addresses']
                all_address_names.update(destinations)
            except Exception:
                pass

        # Look up IP addresses for each address object name
        for addr_name in all_address_names:
            # Skip if it's already an IP address
            try:
                ipaddress.ip_address(addr_name)
                continue  # It's already an IP address
            except Exception:
                pass

            # Look up the address object
            addr_obj = FirewallAddressObject.query.filter_by(
                    name=addr_name,
                    config_file_id=policy.config_file_id
                ).first()
            if addr_obj:
                address_object_mappings[addr_name] = {
                    'ip_address': addr_obj.ip_address,
                    'cidr_notation': addr_obj.cidr_notation,
                    'object_type': addr_obj.object_type
                }
            else:
                # Could be an address group - try policy's config first, then search across all selected configs
                logger.debug(f"DEBUG: Looking up group '{addr_name}' with config_file_id={policy.config_file_id} (policy: {policy.name})")
                addr_group = FirewallAddressGroup.query.filter_by(
                    name=addr_name,
                    config_file_id=policy.config_file_id
                ).first()

                # If group found, check if it contains our searched IP
                # If not, look for the group in other selected configs that does contain it
                def check_ip_in_resolved_members(resolved_list, search_ip):
                    """Check if search IP is in resolved members using proper IP/subnet matching"""
                    for resolved_ip in resolved_list:
                        resolved_str = str(resolved_ip)
                        # Use unified helper function for proper IP/CIDR matching
                        if is_ip_in_cidr_or_exact(search_ip, resolved_str):
                            return True
                    return False

                # If group not found in policy's config, or if it's in global_group_names_with_matches
                # but doesn't contain our IP, look in other selected configs
                if not addr_group:
                    # Group not found in policy's config, look in other selected configs
                    logger.debug(f"DEBUG: Group '{addr_name}' not found in config {policy.config_file_id}, checking other configs")
                    other_groups = FirewallAddressGroup.query.filter(
                        db.and_(
                            FirewallAddressGroup.name == addr_name,
                            FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids)
                        )
                    ).all()

                    # Use the first available version from other configs
                    if other_groups:
                        addr_group = other_groups[0]
                        logger.debug(f"DEBUG: Found group '{addr_name}' in config {addr_group.config_file_id}")

                elif addr_group and addr_group.resolved_members and addr_name in global_group_names_with_matches:
                    # Group found, but check if this version contains our searched IP
                    resolved_ips = json.loads(addr_group.resolved_members)
                    if not check_ip_in_resolved_members(resolved_ips, ip_address):
                        # This version doesn't have our IP, look in other configs
                        logger.debug(f"DEBUG: Group '{addr_name}' in config {policy.config_file_id} doesn't contain {ip_address}, checking other configs")
                        other_groups = FirewallAddressGroup.query.filter(
                            db.and_(
                                FirewallAddressGroup.name == addr_name,
                                FirewallAddressGroup.config_file_id.in_(firewall_config_file_ids),
                                FirewallAddressGroup.config_file_id != policy.config_file_id
                            )
                        ).all()

                        # Find a version that contains our IP
                        for other_group in other_groups:
                            if other_group.resolved_members:
                                other_resolved = json.loads(other_group.resolved_members)
                                if check_ip_in_resolved_members(other_resolved, ip_address):
                                    logger.debug(f"DEBUG: Found group '{addr_name}' in config {other_group.config_file_id} that contains {ip_address}")
                                    addr_group = other_group
                                    break

                if addr_group:
                    logger.debug(f"DEBUG: Found group '{addr_name}' in config {addr_group.config_file.filename}")
                    try:
                        # Use pre-computed resolved members if available
                        if addr_group.resolved_members:
                            resolved_ips = json.loads(addr_group.resolved_members)
                            member_count = addr_group.member_count or len(resolved_ips)

                            # Show group name with member count instead of all IPs
                            group_display = f"{addr_name} ({member_count} members)"

                            # Get detailed member information and flatten for policy display
                            member_details = None
                            hierarchical_members = None
                            if addr_group.member_details:
                                try:
                                    raw_member_details = json.loads(addr_group.member_details)
                                    # Flatten nested groups to show individual IP addresses
                                    member_details = flatten_member_details_for_policy_display(raw_member_details)
                                    # Use natural config hierarchy only - no artificial grouping
                                    hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                except Exception:
                                    member_details = None
                                    hierarchical_members = None

                            address_object_mappings[addr_name] = {
                                'ip_address': group_display,
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_count': member_count,
                                'member_details': member_details,
                                'hierarchical_members': hierarchical_members
                            }
                        else:
                            # Fallback to simple method for groups without pre-computed members
                            members = json.loads(addr_group.members) if isinstance(addr_group.members, str) else addr_group.members
                            member_ips = []
                            for member in members:  # No limit for accuracy
                                member_obj = FirewallAddressObject.query.filter_by(name=member).first()
                                if member_obj and member_obj.ip_address:
                                    member_ips.append(member_obj.ip_address)
                            address_object_mappings[addr_name] = {
                                'ip_address': f"{addr_name} ({len(member_ips)} members)" if member_ips else 'Unknown Group',
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_count': len(member_ips),
                                'member_details': None,
                                'hierarchical_members': None
                            }
                    except Exception:
                        address_object_mappings[addr_name] = {
                            'ip_address': 'Unknown Group',
                            'cidr_notation': None,
                            'object_type': 'group',
                            'member_details': None,
                            'hierarchical_members': None
                        }
                else:
                    # Could be a VIP group - use VIP group from SAME config file as policy
                    vip_group = FirewallVipGroup.query.filter_by(
                        name=addr_name,
                        config_file_id=policy.config_file_id
                    ).first()
                    if vip_group:
                        try:
                            if vip_group.resolved_members:
                                resolved_ips = json.loads(vip_group.resolved_members)
                                member_count = vip_group.member_count or len(resolved_ips)
                                group_display = f"{addr_name} ({member_count} VIPs)"

                                member_details = None
                                hierarchical_members = None
                                if vip_group.member_details:
                                    try:
                                        raw_member_details = json.loads(vip_group.member_details)
                                        member_details = flatten_member_details_for_policy_display(raw_member_details)
                                        hierarchical_members = preserve_group_hierarchy_for_policy_display(raw_member_details)
                                    except Exception:
                                        member_details = None
                                        hierarchical_members = None

                                address_object_mappings[addr_name] = {
                                    'ip_address': group_display,
                                    'cidr_notation': None,
                                    'object_type': 'vip_group',
                                    'member_count': member_count,
                                    'member_details': member_details,
                                    'hierarchical_members': hierarchical_members
                                }
                            else:
                                address_object_mappings[addr_name] = {
                                    'ip_address': f"{addr_name} (VIP Group)",
                                    'cidr_notation': None,
                                    'object_type': 'vip_group',
                                    'member_count': 0,
                                    'member_details': None,
                                    'hierarchical_members': None
                                }
                        except Exception:
                            address_object_mappings[addr_name] = {
                                'ip_address': 'Unknown VIP Group',
                                'cidr_notation': None,
                                'object_type': 'vip_group',
                                'member_details': None,
                                'hierarchical_members': None
                            }

        policy_data['address_mappings'] = address_object_mappings

    # Assign the enhanced paginated_policies to results
    results['policies'] = paginated_policies
    
    # Search NAT policies containing the IP, address objects, or groups with pagination
    try:
        # Build comprehensive search terms for NAT policies (same as object search logic)
        comprehensive_search_terms = set()
        comprehensive_search_terms.add(ip_address)
        comprehensive_search_terms.update(matched_object_names)

        # Add relevant group names from all matched groups
        relevant_group_names = [group_data['name'] for group_data in relevant_groups]
        comprehensive_search_terms.update(relevant_group_names)

        nat_search_conditions = []
        for term in comprehensive_search_terms:
            nat_search_conditions.append(FirewallNatPolicy.source_addresses.like(f'%{term}%'))
            nat_search_conditions.append(FirewallNatPolicy.destination_addresses.like(f'%{term}%'))
            nat_search_conditions.append(FirewallNatPolicy.source_translation.like(f'%{term}%'))
            nat_search_conditions.append(FirewallNatPolicy.destination_translation.like(f'%{term}%'))
        
        if nat_search_conditions:
            # Add config file filtering to NAT policy search
            nat_query_filter = db.and_(
                db.or_(*nat_search_conditions),
                FirewallNatPolicy.config_file_id.in_(firewall_config_file_ids)
            )

            # Get total count for NAT policies
            total_nat_policies = FirewallNatPolicy.query.filter(nat_query_filter).count()

            # Get paginated NAT policy results
            nat_offset = (page - 1) * page_size
            all_nat_policies = FirewallNatPolicy.query.filter(nat_query_filter).offset(nat_offset).limit(page_size).all()
            
            results['pagination']['total_nat_policies'] = total_nat_policies
            results['pagination']['has_more_nat_policies'] = nat_offset + page_size < total_nat_policies
        else:
            all_nat_policies = []
            results['pagination']['total_nat_policies'] = 0
    except Exception as e:
        # Handle case where NAT policies table doesn't exist or is empty
        logger.warning(f"NAT policies not available: {e}")
        all_nat_policies = []
        results['pagination']['total_nat_policies'] = 0
    
    # Use dict to track unique NAT policies by environment and policy identity
    # Key: (environment, policy_id, name, source_zone, dest_zone), Value: latest nat_policy_data
    unique_ip_nat_policies = {}
    
    for nat_policy in all_nat_policies:
        nat_policy_matches = False
        match_details = {'source': [], 'destination': [], 'source_translation': [], 'destination_translation': []}
        
        # Check source addresses (only if search_direction allows it)
        if search_direction in ['both', 'source'] and nat_policy.source_addresses:
            try:
                sources = json.loads(nat_policy.source_addresses) if isinstance(nat_policy.source_addresses, str) else nat_policy.source_addresses
                for src in sources:
                    # Check for exact match, partial match, or object/group match
                    src_matches = False
                    if is_partial_ip(ip_address):
                        # For partial IP, check if source contains the partial pattern
                        src_matches = (src.startswith(ip_address + '.') or
                                     src == ip_address or
                                     src in matched_object_names or
                                     src in relevant_group_names)
                    else:
                        src_matches = (src == ip_address or
                                     src in matched_object_names or
                                     src in relevant_group_names)
                    
                    if src_matches:
                        nat_policy_matches = True
                        match_details['source'].append(src)
            except Exception:
                pass
        
        # Check destination addresses (only if search_direction allows it)
        if search_direction in ['both', 'destination'] and nat_policy.destination_addresses:
            try:
                destinations = json.loads(nat_policy.destination_addresses) if isinstance(nat_policy.destination_addresses, str) else nat_policy.destination_addresses
                for dst in destinations:
                    # Check for exact match, partial match, or object/group match
                    dst_matches = False
                    if is_partial_ip(ip_address):
                        # For partial IP, check if destination contains the partial pattern
                        dst_matches = (dst.startswith(ip_address + '.') or
                                     dst == ip_address or
                                     dst in matched_object_names or
                                     dst in relevant_group_names)
                    else:
                        dst_matches = (dst == ip_address or
                                     dst in matched_object_names or
                                     dst in relevant_group_names)
                    
                    if dst_matches:
                        nat_policy_matches = True
                        match_details['destination'].append(dst)
            except Exception:
                pass
        
        # Check source translation addresses
        if nat_policy.source_translation:
            try:
                source_trans = json.loads(nat_policy.source_translation) if isinstance(nat_policy.source_translation, str) else nat_policy.source_translation
                # Handle different translation formats
                translation_ips = []
                if isinstance(source_trans, dict):
                    # FortiGate format: {"translated_ip": "x.x.x.x", "type": "static"}
                    if 'translated_ip' in source_trans:
                        translation_ips.append(source_trans['translated_ip'])
                    # Palo Alto format: {"type": "dynamic-ip-and-port", "translated_address": "x.x.x.x"}
                    elif 'translated_address' in source_trans:
                        translation_ips.append(source_trans['translated_address'])
                elif isinstance(source_trans, list):
                    # Array of IPs
                    translation_ips.extend(source_trans)
                elif isinstance(source_trans, str):
                    # Direct IP string
                    translation_ips.append(source_trans)
                
                for trans_ip in translation_ips:
                    if (trans_ip == ip_address or 
                        trans_ip in matched_object_names or 
                        trans_ip in relevant_groups):
                        nat_policy_matches = True
                        match_details['source_translation'].append(trans_ip)
            except Exception:
                pass
        
        # Check destination translation addresses
        if nat_policy.destination_translation:
            try:
                dest_trans = json.loads(nat_policy.destination_translation) if isinstance(nat_policy.destination_translation, str) else nat_policy.destination_translation
                # Handle different translation formats
                translation_ips = []
                if isinstance(dest_trans, dict):
                    # FortiGate format: {"translated_ip": "x.x.x.x", "type": "static"}
                    if 'translated_ip' in dest_trans:
                        translation_ips.append(dest_trans['translated_ip'])
                    # Palo Alto format: {"type": "static", "translated_address": "x.x.x.x"}
                    elif 'translated_address' in dest_trans:
                        translation_ips.append(dest_trans['translated_address'])
                elif isinstance(dest_trans, list):
                    # Array of IPs
                    translation_ips.extend(dest_trans)
                elif isinstance(dest_trans, str):
                    # Direct IP string
                    translation_ips.append(dest_trans)
                
                for trans_ip in translation_ips:
                    if (trans_ip == ip_address or 
                        trans_ip in matched_object_names or 
                        trans_ip in relevant_groups):
                        nat_policy_matches = True
                        match_details['destination_translation'].append(trans_ip)
            except Exception:
                pass
        
        if nat_policy_matches:
            nat_policy_data = nat_policy.serialize
            nat_policy_data['match_details'] = match_details
            
            # Add IP address mappings for all address objects in this NAT policy
            address_object_mappings = {}
            
            # Get all unique address object names from source and destination
            all_address_names = set()
            try:
                if nat_policy.source_addresses:
                    sources = json.loads(nat_policy.source_addresses) if isinstance(nat_policy.source_addresses, str) else nat_policy.source_addresses
                    all_address_names.update(sources)
            except Exception:
                pass
            
            try:
                if nat_policy.destination_addresses:
                    destinations = json.loads(nat_policy.destination_addresses) if isinstance(nat_policy.destination_addresses, str) else nat_policy.destination_addresses
                    all_address_names.update(destinations)
            except Exception:
                pass
            
            # Look up IP addresses for each address object name
            for addr_name in all_address_names:
                # Skip if it's already an IP address
                try:
                    ipaddress.ip_address(addr_name)
                    continue  # It's already an IP address
                except Exception:
                    pass
                
                # Look up the address object
                addr_obj = FirewallAddressObject.query.filter_by(
                    name=addr_name,
                    config_file_id=policy.config_file_id
                ).first()
                if addr_obj:
                    address_object_mappings[addr_name] = {
                        'ip_address': addr_obj.ip_address,
                        'cidr_notation': addr_obj.cidr_notation,
                        'object_type': addr_obj.object_type
                    }
                else:
                    # Could be an address group
                    addr_group = FirewallAddressGroup.query.join(ConfigFile).filter(FirewallAddressGroup.name == addr_name).order_by(ConfigFile.upload_date.desc()).first()
                    if addr_group and addr_group.members:
                        try:
                            members = json.loads(addr_group.members) if isinstance(addr_group.members, str) else addr_group.members
                            member_ips = []
                            
                            def resolve_nat_address_member(member_name, visited=None):
                                """Recursively resolve address group members to IP addresses"""
                                if visited is None:
                                    visited = set()
                                
                                # Prevent infinite recursion in case of circular references
                                if member_name in visited:
                                    return [f"Circular: {member_name}"]
                                
                                visited.add(member_name)
                                
                                # First check if it's a regular address object
                                member_obj = FirewallAddressObject.query.filter_by(name=member_name).first()
                                if member_obj:
                                    # Prioritize cidr_notation over ip_address for proper subnet prefix display
                                    display_ip = member_obj.cidr_notation or member_obj.ip_address
                                    # If only ip_address and it's a host object, add /32
                                    if not member_obj.cidr_notation and member_obj.ip_address and member_obj.object_type == 'host':
                                        display_ip = f"{member_obj.ip_address}/32"
                                    return [display_ip]
                                
                                # If not found as address object, check if it's a nested address group
                                nested_group = FirewallAddressGroup.query.join(ConfigFile).filter(FirewallAddressGroup.name == member_name).order_by(ConfigFile.upload_date.desc()).first()
                                if nested_group and nested_group.members:
                                    try:
                                        nested_members = json.loads(nested_group.members) if isinstance(nested_group.members, str) else nested_group.members
                                        resolved_ips = []
                                        for nested_member in nested_members:
                                            resolved_ips.extend(resolve_nat_address_member(nested_member, visited.copy()))
                                        return resolved_ips
                                    except Exception:
                                        return [f"Error: {member_name}"]
                                
                                # If not found anywhere, return the name (could be missing from database)
                                return [f"Missing: {member_name}"]
                            
                            # Resolve all members (including nested groups)
                            for member in members:
                                member_ips.extend(resolve_nat_address_member(member))
                            
                            # Format group display - show group name with member count
                            if member_ips:
                                group_display = f"{addr_name} ({len(member_ips)} members)"
                            else:
                                group_display = f"{addr_name} (0 members)"

                            # Get detailed member information and flatten for policy display
                            member_details = None
                            if addr_group.member_details:
                                try:
                                    raw_member_details = json.loads(addr_group.member_details)
                                    # Flatten nested groups to show individual IP addresses
                                    member_details = flatten_member_details_for_policy_display(raw_member_details)
                                except Exception:
                                    member_details = None

                            address_object_mappings[addr_name] = {
                                'ip_address': group_display,
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_count': len(member_ips),
                                'member_details': member_details
                            }
                        except Exception:
                            # Even if we can't parse members, try to get member_details
                            member_details = None
                            if addr_group.member_details:
                                try:
                                    raw_member_details = json.loads(addr_group.member_details)
                                    # Flatten nested groups to show individual IP addresses
                                    member_details = flatten_member_details_for_policy_display(raw_member_details)
                                except Exception:
                                    member_details = None

                            address_object_mappings[addr_name] = {
                                'ip_address': 'Unknown Group',
                                'cidr_notation': None,
                                'object_type': 'group',
                                'member_details': member_details
                            }

            nat_policy_data['address_mappings'] = address_object_mappings
            
            # Get environment name for deduplication
            env_name = "Unknown"
            if nat_policy.config_file:
                filename = nat_policy.config_file.filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'DELTA-FW01' in filename:
                    env_name = "UAT FW"
                elif 'DELTA-ADMIN-FW01' in filename:
                    env_name = "Admin FW"
            
            # Create unique key for deduplication
            policy_key = (
                env_name,
                nat_policy.policy_id,
                nat_policy.name,
                nat_policy.source_zone,
                nat_policy.destination_zone
            )
            
            # Keep only the most recent version (highest config file ID)
            if policy_key not in unique_ip_nat_policies:
                unique_ip_nat_policies[policy_key] = nat_policy_data
            else:
                existing_policy_data = unique_ip_nat_policies[policy_key]
                if nat_policy.config_file_id > existing_policy_data.get('config_file_id', 0):
                    unique_ip_nat_policies[policy_key] = nat_policy_data
    
    # Add deduplicated NAT policies to results
    for nat_policy_data in unique_ip_nat_policies.values():
        results['nat_policies'].append(nat_policy_data)
    
    return results

def extract_vs_references_from_firewall_results(firewall_results):
    """Extract virtual server references from firewall policies and NAT policies"""
    vs_references = set()

    # Only extract VS references from NAT policies where there's an actual translation
    # This ensures we only show LTM results when there's a real NAT mapping from public IP to VS
    for nat_policy in firewall_results.get('nat_policies', []):
        # Only extract from destination_translation, not from general address_mappings
        if 'destination_translation' in nat_policy:
            dest_translation = nat_policy.get('destination_translation', {})

            # Handle both string (JSON) and dict formats
            if isinstance(dest_translation, str):
                import json
                try:
                    dest_translation = json.loads(dest_translation)
                except Exception:
                    continue

            if isinstance(dest_translation, dict) and 'translated_address' in dest_translation:
                translated_addr = dest_translation['translated_address']
                # Extract the base IP from formats like "10.0.0.9_32" or "10.1.2.87_32"
                if isinstance(translated_addr, str):
                    base_ip = translated_addr.split('_')[0]
                    # Only add if it's a private IP that could be a VS destination
                    # IMPORTANT: Use RFC 1918 private IP detection instead of hardcoded prefixes
                    # This ensures ALL private IPs are recognized, not just specific subnets
                    # Previously hardcoded to '10.15.' and '172.20.' which missed IPs like 10.1.x.x
                    try:
                        import ipaddress
                        ip_obj = ipaddress.ip_address(base_ip)
                        # Check if it's RFC 1918 private IP (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
                        if ip_obj.is_private:
                            vs_references.add(base_ip)
                    except ValueError:
                        # Not a valid IP, skip it
                        pass

    return list(vs_references)

def search_ltm_by_translated_ips(translated_ips):
    """Search for LTM virtual servers by their destination IPs (from NAT translations)"""
    # ConfigFile already imported at top
    from sqlalchemy import func

    # Get latest LTM config files
    latest_config_files = db.session.query(
        func.regexp_replace(ConfigFile.filename, r'_\d{8}-\d{4}\.txt$', '').label('system_name'),
        func.max(ConfigFile.id).label('max_id')
    ).filter(
        db.or_(
            ConfigFile.filename.like('%LTM%'),
            ConfigFile.filename.like('H2SLB01%'),
            ConfigFile.filename.like('%SLB%')
        )
    ).group_by(func.regexp_replace(ConfigFile.filename, r'_\d{8}-\d{4}\.txt$', '')).all()

    latest_config_file_ids = [cf.max_id for cf in latest_config_files]

    virtual_servers = {}
    pools_and_nodes = {}

    # Search for virtual servers by their destination IP addresses
    for translated_ip in translated_ips:
        vs_matches = LtmVirtualServer.query.filter(
            db.and_(
                db.or_(
                    LtmVirtualServer.destination_ip == translated_ip,
                    LtmVirtualServer.destination_ip == f"/Common/{translated_ip}"
                ),
                LtmVirtualServer.config_file_id.in_(latest_config_file_ids)
            )
        ).all()
        
        for vs in vs_matches:
            vs_data = vs.serialize
            vs_data['status'] = 'enabled' if vs.enabled else 'disabled'
            vs_data['cross_referenced'] = True  # Mark as cross-referenced from firewall
            
            # Get all nodes for this VS's pool
            pool_nodes = []
            unique_nodes = {}
            if vs.pool_name:
                pools = LtmPool.query.filter(
                    db.and_(
                        LtmPool.name == vs.pool_name,
                        LtmPool.config_file_id.in_(latest_config_file_ids)
                    )
                ).all()
                for pool in pools:
                    nodes = LtmNode.query.filter(
                        db.and_(
                            LtmNode.pool_id == pool.id,
                            LtmNode.config_file_id.in_(latest_config_file_ids)
                        )
                    ).all()
                    for node in nodes:
                        node_key = f"{node.ip_address}:{node.port}"
                        if node_key not in unique_nodes:
                            node_data = node.serialize
                            node_data['cross_referenced'] = True
                            unique_nodes[node_key] = node_data
                
                pool_nodes = list(unique_nodes.values())
            
            unique_key = f"{vs.name}_{vs.destination_ip}_{vs.destination_port}"
            virtual_servers[unique_key] = {
                'virtual_server': vs_data,
                'pool_nodes': pool_nodes
            }
    
    return {
        'virtual_servers': list(virtual_servers.values()),
        'pools_and_nodes': []
    }

def merge_ltm_results(original_results, cross_referenced_results):
    """Merge original LTM results with cross-referenced results"""
    # Use a dictionary to ensure proper deduplication
    unique_virtual_servers = {}

    # Add original virtual servers first
    for vs_data in original_results.get('virtual_servers', []):
        vs = vs_data['virtual_server']
        # Clean and normalize the key components to handle any inconsistencies
        name = str(vs.get('name', '')).strip()
        dest_ip = str(vs.get('destination_ip', '')).strip()
        dest_port = str(vs.get('destination_port', '')).strip()

        key = f"{name}_{dest_ip}_{dest_port}"
        unique_virtual_servers[key] = vs_data

    # Add cross-referenced virtual servers (avoid duplicates)
    for vs_data in cross_referenced_results.get('virtual_servers', []):
        vs = vs_data['virtual_server']
        # Clean and normalize the key components to handle any inconsistencies
        name = str(vs.get('name', '')).strip()
        dest_ip = str(vs.get('destination_ip', '')).strip()
        dest_port = str(vs.get('destination_port', '')).strip()

        key = f"{name}_{dest_ip}_{dest_port}"
        if key not in unique_virtual_servers:
            unique_virtual_servers[key] = vs_data

    merged_results = {
        'virtual_servers': list(unique_virtual_servers.values()),
        'pools_and_nodes': original_results.get('pools_and_nodes', []).copy()
    }

    return merged_results

def query_fqdn_database(search_term):
    """Query the external FQDN database"""
    try:
        import ipaddress as ip_utils

        connection = fqdn_db_connection()
        cursor = connection.cursor()

        # Check if search_term is an IP address
        is_ip = False
        try:
            ip_utils.ip_address(search_term.strip())
            is_ip = True
        except ValueError:
            pass

        if is_ip:
            # For IP addresses, use exact match to avoid false positives
            # e.g., 203.0.113.36 should NOT match 203.0.113.360, 203.0.113.361, etc.
            cursor.execute("""
                SELECT id, owner, domain, fqdn, ttl, type_, ip, geoInfo
                FROM fqdn_new
                WHERE ip = %s
                ORDER BY fqdn
            """, (search_term.strip(),))
        else:
            # For domain/FQDN searches, use pattern matching
            search_pattern = f"%{search_term}%"
            cursor.execute("""
                SELECT id, owner, domain, fqdn, ttl, type_, ip, geoInfo
                FROM fqdn_new
                WHERE domain LIKE %s
                   OR fqdn LIKE %s
                ORDER BY fqdn
            """, (search_pattern, search_pattern))
        
        results = cursor.fetchall()
        
        # Convert to list of dictionaries
        fqdn_records = []
        for row in results:
            fqdn_records.append({
                'id': row[0],
                'owner': row[1],
                'domain': row[2], 
                'fqdn': row[3],
                'ttl': row[4],
                'type': row[5],
                'ip': row[6],
                'geo_info': row[7]
            })
        
        connection.close()
        return {
            'success': True,
            'records': fqdn_records,
            'count': len(fqdn_records)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'records': [],
            'count': 0
        }

def query_slbs_by_fqdn_pattern(fqdn, infrastructure_filter=None):
    """
    Query slbs table using FQDN naming pattern matching (like fqdn_compare tool).

    This function implements the same search logic as fqdn_compare:
    - Extracts subdomain from FQDN
    - Creates abbreviation pattern (e.g., sb-results -> SBR)
    - Searches slbs table for matching Virtual Server names

    Args:
        fqdn: Full qualified domain name (e.g., sb-results.demo-corp.example)
        infrastructure_filter: List of environment names to filter by

    Returns:
        dict with success, virtual_servers list, and count
    """
    try:
        import pymysql
        import json

        connection = fqdn_db_connection()
        cursor = connection.cursor()

        # Parse FQDN to extract subdomain
        parts = fqdn.split('.')
        if len(parts) < 2:
            return {'success': True, 'virtual_servers': [], 'count': 0, 'source': 'slbs'}

        subdomain = parts[0]

        # Generate search patterns
        search_patterns = set()

        # Pattern 1: Full subdomain
        search_patterns.add(subdomain)

        # Pattern 2: If subdomain has hyphens, create abbreviation
        if '-' in subdomain:
            words = subdomain.split('-')
            # Abbreviation strategy: S-B-R for sb-results
            abbr = ''.join(w[0:2].upper() if i == 0 else w[0].upper()
                          for i, w in enumerate(words))
            search_patterns.add(abbr)

        # Map infrastructure filter to v_env values
        # v_env mapping: 1=Alpha, 2=Bravo, 3=Charlie, 4=Delta, 5=UAT, 6=ADMIN, 7=LOADTEST
        env_map = {
            'ALPHA': 1, 'BRAVO': 2, 'CHARLIE': 3, 'DELTA': 4,
            'UAT': 5, 'ADMIN': 6, 'LOADTEST': 7
        }

        env_filter = []
        if infrastructure_filter:
            for env_name in infrastructure_filter:
                if env_name in env_map:
                    env_filter.append(env_map[env_name])

        # If no filter or filter includes all, search all environments
        if not env_filter:
            env_filter = list(env_map.values())

        # Search slbs table for each pattern
        all_virtual_servers = {}

        for pattern in search_patterns:
            # Build WHERE clause
            where_clause = "v_name LIKE %s AND v_env IN ({})".format(
                ','.join(['%s'] * len(env_filter))
            )
            params = [f"%{pattern}%"] + env_filter

            cursor.execute(f"""
                SELECT id, v_name, v_ip, v_service, v_pool, v_env
                FROM slbs
                WHERE {where_clause}
                ORDER BY v_name
            """, params)

            results = cursor.fetchall()

            for row in results:
                vs_id, v_name, v_ip, v_service, v_pool_json, v_env = row

                # Parse pool data
                pool_name = None
                pool_members = []
                try:
                    v_pool = json.loads(v_pool_json)
                    if v_pool and len(v_pool) > 0:
                        pool_name = v_pool[0]
                        pool_members = [
                            {'ip_address': member.split(':')[0],
                             'port': member.split(':')[1] if ':' in member else ''}
                            for member in v_pool[1:] if ':' in member
                        ]
                except Exception:
                    pass

                # Map v_env back to environment name
                env_name = None
                for name, env_id in env_map.items():
                    if env_id == v_env:
                        env_name = {'ALPHA': 'Alpha', 'BRAVO': 'Bravo', 'CHARLIE': 'Charlie'}.get(name, name)
                        break

                # Create unique key
                vs_key = f"{v_name}_{v_ip}_{v_service}"

                if vs_key not in all_virtual_servers:
                    all_virtual_servers[vs_key] = {
                        'virtual_server': {
                            'id': vs_id,
                            'name': v_name,
                            'destination_ip': v_ip,
                            'destination_port': v_service,
                            'pool_name': pool_name,
                            'enabled': True,
                            'status': 'enabled',
                            'source': 'slbs',  # Mark source as slbs table
                            'environment': env_name,
                            'matched_pattern': pattern  # Track which pattern matched
                        },
                        'pool_nodes': pool_members
                    }

        connection.close()

        virtual_servers_list = list(all_virtual_servers.values())

        return {
            'success': True,
            'virtual_servers': virtual_servers_list,
            'count': len(virtual_servers_list),
            'source': 'slbs',
            'patterns_used': list(search_patterns)
        }

    except Exception as e:
        logger.warning(f"Error querying slbs table: {e}")
        return {
            'success': False,
            'error': str(e),
            'virtual_servers': [],
            'count': 0,
            'source': 'slbs'
        }

def find_vs_for_pool_member(pool_member_ip, infrastructure_filter=None):
    """Find virtual servers that have this IP as a pool member and resolve their names to get FQDN results"""
    try:
        # Get config file IDs filtered by infrastructure
        config_file_ids = get_infrastructure_config_file_ids(infrastructure_filter)

        # Find all virtual servers where this IP appears as a pool member
        virtual_servers_with_member = []

        # Search in LTM nodes for this IP
        nodes = LtmNode.query.filter(
            db.and_(
                LtmNode.ip_address == pool_member_ip,
                LtmNode.config_file_id.in_(config_file_ids)
            )
        ).all()

        # For each node, find the pool it belongs to, then find virtual servers that use this pool
        vs_names_found = set()
        for node in nodes:
            if node.pool:
                # Find virtual servers that use this pool
                virtual_servers = LtmVirtualServer.query.filter(
                    db.and_(
                        LtmVirtualServer.pool_name == node.pool.name,
                        LtmVirtualServer.config_file_id.in_(config_file_ids)
                    )
                ).all()

                for vs in virtual_servers:
                    if vs.name not in vs_names_found:
                        vs_names_found.add(vs.name)
                        virtual_servers_with_member.append({
                            'vs_name': vs.name,
                            'vs_ip': vs.destination_ip,
                            'pool_name': vs.pool_name,
                            'pool_member_ip': pool_member_ip
                        })

        # Now resolve each VS name to get FQDN results
        all_fqdn_results = {'success': True, 'records': [], 'count': 0}

        if virtual_servers_with_member:
            for vs_info in virtual_servers_with_member:
                vs_name = vs_info['vs_name']

                # Try to resolve the VS name to get public IP and FQDN results
                resolution_result = resolve_object_to_ip(vs_name, infrastructure_filter)
                if resolution_result['success'] and resolution_result['resolved_ips']:
                    # Get FQDN results for the resolved IPs
                    for resolved_ip in resolution_result['resolved_ips']:
                        fqdn_result = query_fqdn_database(resolved_ip)
                        if fqdn_result['success'] and fqdn_result['records']:
                            all_fqdn_results['records'].extend(fqdn_result['records'])

            # Remove duplicates based on FQDN + IP combination
            unique_fqdn_records = []
            seen_combinations = set()
            for record in all_fqdn_results['records']:
                combination = f"{record['fqdn']}-{record['ip']}"
                if combination not in seen_combinations:
                    seen_combinations.add(combination)
                    unique_fqdn_records.append(record)

            all_fqdn_results['records'] = unique_fqdn_records
            all_fqdn_results['count'] = len(unique_fqdn_records)

        return {
            'success': True,
            'virtual_servers': virtual_servers_with_member,
            'vs_fqdn_results': all_fqdn_results,
            'count': len(virtual_servers_with_member)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'virtual_servers': [],
            'vs_fqdn_results': {'success': False, 'records': [], 'count': 0},
            'count': 0
        }

def resolve_object_to_ip(object_name, infrastructure_filter=None):
    """Resolve object name to IP address(es) it represents"""
    logger.debug(f"DEBUG: resolve_object_to_ip called with object_name='{object_name}', infrastructure_filter={infrastructure_filter}")
    try:
        # Search in address objects for direct matches
        resolved_ips = set()

        # Get config file IDs filtered by infrastructure
        config_file_ids = get_infrastructure_config_file_ids(infrastructure_filter)

        # CRITICAL FIX: Use exact match instead of wildcard LIKE to prevent matching thousands of unrelated objects
        # For VS names and specific objects, we want exact matches only
        # Wildcard matching (%object_name%) was causing 1636+ false matches
        address_objects = FirewallAddressObject.query.filter(
            db.and_(
                FirewallAddressObject.name == object_name,  # Exact match only
                FirewallAddressObject.config_file_id.in_(config_file_ids)
            )
        ).all()

        for addr_obj in address_objects:
            if addr_obj.ip_address:
                # Keep full CIDR notation for expansion later
                resolved_ips.add(addr_obj.ip_address)  # Keep CIDR notation intact

            # Also check cidr_notation field if it exists separately
            if hasattr(addr_obj, 'cidr_notation') and addr_obj.cidr_notation:
                resolved_ips.add(addr_obj.cidr_notation)

        # Also search in firewall address groups (exact match)
        address_groups = FirewallAddressGroup.query.filter(
            db.and_(
                FirewallAddressGroup.name == object_name,  # Exact match only
                FirewallAddressGroup.config_file_id.in_(config_file_ids)
            )
        ).all()

        for addr_group in address_groups:
            # Parse resolved_members to get CIDR ranges/IPs
            if addr_group.resolved_members:
                import json
                try:
                    resolved_members = json.loads(addr_group.resolved_members)
                    for member_ip in resolved_members:
                        resolved_ips.add(member_ip)
                        logger.debug(f"DEBUG: Added IP from address group '{object_name}': {member_ip}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"DEBUG: Failed to parse resolved_members for group '{object_name}': {e}")

        # Search in LTM virtual servers for object names
        logger.debug(f"DEBUG: Searching LTM virtual servers for object_name='{object_name}'")
        # CRITICAL FIX: Use exact match or prefix match instead of wildcard LIKE
        # Try exact match first, then with /Common/ prefix
        ltm_virtual_servers = LtmVirtualServer.query.filter(
            db.and_(
                db.or_(
                    LtmVirtualServer.name == object_name,
                    LtmVirtualServer.name == f'/Common/{object_name}'
                ),
                LtmVirtualServer.config_file_id.in_(config_file_ids)
            )
        ).all()
        logger.debug(f"DEBUG: Found {len(ltm_virtual_servers)} LTM virtual servers")

        for vs in ltm_virtual_servers:
            logger.debug(f"DEBUG: LTM VS found: {vs.name} -> {vs.destination_ip}")
            if vs.destination_ip:
                resolved_ips.add(vs.destination_ip)

        # NEW: Look up NAT translations for all resolved IPs to find corresponding public IPs
        # This will help find FQDN records for objects like a virtual server
        all_ips_with_nat = set(resolved_ips)  # Start with the resolved private IPs
        logger.debug(f"DEBUG: resolve_object_to_ip for '{object_name}' found initial IPs: {resolved_ips}")

        for ip in list(resolved_ips):
            try:
                # Clean up the IP (remove /Common/ prefix if present)
                clean_ip = ip.replace('/Common/', '')
                logger.debug(f"DEBUG: Looking up NAT translations for IP: {ip} (cleaned: {clean_ip})")

                # Try both the original IP and cleaned IP for NAT translations
                for search_ip in [ip, clean_ip]:
                    nat_result = find_nat_translations(search_ip, infrastructure_filter)
                    logger.debug(f"DEBUG: NAT result for {search_ip}: success={nat_result.get('success')}, mappings_count={len(nat_result.get('mappings', []))}")
                    if nat_result['success'] and nat_result['mappings']:
                        # Add all mapped public IPs to the resolved IPs set
                        for mapping in nat_result['mappings']:
                            if 'mapped_public_ips' in mapping:
                                for public_ip in mapping['mapped_public_ips']:
                                    logger.debug(f"DEBUG: Adding NAT-translated public IP: {public_ip}")
                                    all_ips_with_nat.add(public_ip)
                        break  # Found mappings, no need to try other formats

                # IMPORTANT: Also search by the actual LTM virtual server names found
                # The NAT policies often reference the VS names, not the resolved IPs
                ltm_vs_query = LtmVirtualServer.query.filter(LtmVirtualServer.name.ilike(f'%{object_name}%'))
                if infrastructure_filter:
                    ltm_config_files = ConfigFile.query.filter(
                        db.or_(*[ConfigFile.filename.ilike(f'%{infra}%') for infra in infrastructure_filter])
                    ).all()
                    ltm_config_file_ids = [cf.id for cf in ltm_config_files]
                    ltm_vs_query = ltm_vs_query.filter(LtmVirtualServer.config_file_id.in_(ltm_config_file_ids))

                ltm_virtual_servers = ltm_vs_query.all()
                logger.debug(f"DEBUG: Found {len(ltm_virtual_servers)} LTM virtual servers to check for NAT policies")

                for vs in ltm_virtual_servers:
                    # Try NAT lookup using the exact VS name from LTM
                    vs_name = vs.name
                    if vs_name.startswith('/Common/'):
                        clean_vs_name = vs_name.replace('/Common/', '')
                    else:
                        clean_vs_name = vs_name

                    logger.debug(f"DEBUG: Checking NAT policies for VS name: '{vs_name}' (cleaned: '{clean_vs_name}')")

                    for search_name in [vs_name, clean_vs_name]:
                        nat_result_by_vs_name = find_nat_translations(search_name, infrastructure_filter)
                        logger.debug(f"DEBUG: NAT result for VS name '{search_name}': success={nat_result_by_vs_name.get('success')}, mappings_count={len(nat_result_by_vs_name.get('mappings', []))}")
                        if nat_result_by_vs_name['success'] and nat_result_by_vs_name['mappings']:
                            for mapping in nat_result_by_vs_name['mappings']:
                                if 'mapped_public_ips' in mapping:
                                    for public_ip in mapping['mapped_public_ips']:
                                        logger.debug(f"DEBUG: Adding NAT-translated public IP from VS name '{search_name}': {public_ip}")
                                        all_ips_with_nat.add(public_ip)
                            break  # Found mappings, no need to try other name formats
            except Exception as e:
                # Log NAT lookup error but continue
                logger.warning(f"NAT lookup failed for {ip}: {e}")
                continue

        logger.debug(f"DEBUG: Final IPs for '{object_name}': {all_ips_with_nat}")

        # Apply CIDR expansion to get individual IPs from CIDR ranges
        expanded_ips = expand_cidr_ranges(list(all_ips_with_nat))
        logger.debug(f"DEBUG: After CIDR expansion for '{object_name}': {expanded_ips}")

        return {
            'success': True,
            'resolved_ips': expanded_ips,
            'count': len(expanded_ips)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'resolved_ips': [],
            'count': 0
        }

def find_nat_translations(private_ip, infrastructure_filter=None):
    """Find NAT policy translations that map a private IP to public IPs"""
    try:
        import ipaddress as ip_utils

        # Clean the IP input (remove /Common/ prefix if present)
        clean_private_ip = private_ip.replace('/Common/', '') if private_ip else ''
        logger.debug(f"DEBUG NAT: find_nat_translations called with private_ip='{private_ip}', cleaned='{clean_private_ip}', infrastructure_filter={infrastructure_filter}")

        # Build query conditions for NAT policies containing the private IP
        nat_policies_query = FirewallNatPolicy.query

        # Filter by infrastructure if specified
        if infrastructure_filter:
            # Handle infrastructure_filter as a list of infrastructure names
            infrastructure_conditions = []
            if isinstance(infrastructure_filter, list):
                for infra in infrastructure_filter:
                    infrastructure_conditions.append(ConfigFile.filename.ilike(f'%{infra}%'))
            else:
                infrastructure_conditions.append(ConfigFile.filename.ilike(f'%{infrastructure_filter}%'))

            firewall_config_files = ConfigFile.query.filter(db.or_(*infrastructure_conditions)).all()
            firewall_config_file_ids = [cf.id for cf in firewall_config_files]
            nat_policies_query = nat_policies_query.filter(
                FirewallNatPolicy.config_file_id.in_(firewall_config_file_ids)
            )
            logger.debug(f"DEBUG NAT: Found {len(firewall_config_file_ids)} firewall config files for infrastructure filter: {[cf.filename for cf in firewall_config_files[:5]]}")  # Show first 5 filenames

        # First, find object names that resolve to the private IP (try both original and cleaned IP)
        search_ips = [private_ip, clean_private_ip] if clean_private_ip != private_ip else [private_ip]

        all_private_ip_objects = []
        for search_ip in search_ips:
            private_ip_objects = FirewallAddressObject.query.filter(
                db.or_(
                    FirewallAddressObject.ip_address == search_ip,
                    FirewallAddressObject.cidr_notation.like(f'%{search_ip}%')
                )
            ).all()
            all_private_ip_objects.extend(private_ip_objects)

        private_ip_object_names = [obj.name for obj in all_private_ip_objects]
        logger.debug(f"DEBUG NAT: Found {len(private_ip_object_names)} private IP objects: {private_ip_object_names}")

        # Search for NAT policies in multiple ways:
        # 1. Direct IP reference in translations
        # 2. Object name reference in source/destination addresses
        # 3. Object name reference in translations
        search_conditions = []

        # Direct IP search in source/destination addresses and translations (try both original and cleaned)
        for search_ip in search_ips:
            search_conditions.append(FirewallNatPolicy.source_addresses.like(f'%{search_ip}%'))
            search_conditions.append(FirewallNatPolicy.destination_addresses.like(f'%{search_ip}%'))
            search_conditions.append(FirewallNatPolicy.source_translation.like(f'%{search_ip}%'))
            search_conditions.append(FirewallNatPolicy.destination_translation.like(f'%{search_ip}%'))

        # Object name search
        for obj_name in private_ip_object_names:
            search_conditions.append(FirewallNatPolicy.source_addresses.like(f'%{obj_name}%'))
            search_conditions.append(FirewallNatPolicy.destination_addresses.like(f'%{obj_name}%'))
            search_conditions.append(FirewallNatPolicy.source_translation.like(f'%{obj_name}%'))
            search_conditions.append(FirewallNatPolicy.destination_translation.like(f'%{obj_name}%'))

        logger.debug(f"DEBUG NAT: Created {len(search_conditions)} search conditions")

        if not search_conditions:
            logger.debug(f"DEBUG NAT: No search conditions, returning empty mappings")
            return {'success': True, 'mappings': [], 'count': 0}

        nat_policies = nat_policies_query.filter(db.or_(*search_conditions)).all()
        logger.debug(f"DEBUG NAT: Found {len(nat_policies)} NAT policies")

        nat_mappings = []

        for policy in nat_policies:
            logger.debug(f"DEBUG NAT: Processing policy '{policy.name}' (ID: {policy.policy_id})")
            logger.debug(f"DEBUG NAT: Source translation: {policy.source_translation}")
            logger.debug(f"DEBUG NAT: Destination translation: {policy.destination_translation}")

            # Parse source and destination translation JSON
            source_translation = {}
            destination_translation = {}

            try:
                if policy.source_translation:
                    source_translation = json.loads(policy.source_translation)
                if policy.destination_translation:
                    destination_translation = json.loads(policy.destination_translation)
            except Exception as e:
                logger.debug(f"DEBUG NAT: Error parsing translations for policy {policy.name}: {e}")
                continue

            # Extract mapped IPs from translations
            mapped_ips = []
            mapping_type = None

            # Check for Source NAT (private -> public)
            if source_translation:
                if 'translated_ip' in source_translation:
                    mapped_ips.append(source_translation['translated_ip'])
                    mapping_type = 'Source NAT'
                if 'translated_address' in source_translation:
                    mapped_ips.append(source_translation['translated_address'])
                    mapping_type = 'Source NAT'

            # Check for Destination NAT (public -> private)
            # In DNAT, the destination gets translated TO the private IP
            # So we need to find the public IP being accessed
            if destination_translation:
                # If destination is being translated TO our private IP,
                # then the original destination is the public IP
                dest_translated = destination_translation.get('translated_address', '')
                # Handle both direct IP matches and object name matches
                dest_match = False
                logger.debug(f"DEBUG NAT: Checking destination match for policy {policy.name}")
                logger.debug(f"DEBUG NAT: dest_translated='{dest_translated}', clean_private_ip='{clean_private_ip}', private_ip='{private_ip}'")

                if clean_private_ip in dest_translated or private_ip in dest_translated:
                    dest_match = True
                    logger.debug(f"DEBUG NAT: Direct IP match found")
                elif any(obj_name in dest_translated for obj_name in private_ip_object_names):
                    dest_match = True
                    logger.debug(f"DEBUG NAT: Object name match found")
                # Also check if the translated address is an object that resolves to our IP
                elif dest_translated:
                    # Check if dest_translated is an object name that resolves to our private IP
                    clean_dest = dest_translated.replace('_32', '').replace('_', '.')
                    logger.debug(f"DEBUG NAT: Checking cleaned dest: '{clean_dest}' == '{clean_private_ip}'")
                    if clean_dest == clean_private_ip:
                        dest_match = True
                        logger.debug(f"DEBUG NAT: Cleaned destination match found")

                logger.debug(f"DEBUG NAT: dest_match = {dest_match}")

                if dest_match:
                    # Get the public IP from destination addresses
                    try:
                        dest_addrs = json.loads(policy.destination_addresses) if policy.destination_addresses else []
                        logger.debug(f"DEBUG NAT: Found destination match! Processing {len(dest_addrs)} destination addresses: {dest_addrs}")
                        for addr in dest_addrs:
                            # First try to resolve as address object
                            addr_obj = FirewallAddressObject.query.filter_by(name=addr).first()
                            if addr_obj and addr_obj.ip_address:
                                mapped_ips.append(addr_obj.ip_address)
                                mapping_type = 'Destination NAT'
                            else:
                                # Try to resolve as address group
                                logger.debug(f"DEBUG NAT: Looking for address group '{addr}'")
                                # First try to find address group from the same config file as the NAT policy
                                addr_group = FirewallAddressGroup.query.filter_by(
                                    name=addr,
                                    config_file_id=policy.config_file_id
                                ).first()

                                # If not found in same config file, try any config file but prefer ones with members
                                if not addr_group:
                                    addr_groups = FirewallAddressGroup.query.filter_by(name=addr).all()
                                    # Sort by member count (prefer groups with actual members)
                                    addr_groups_with_members = [ag for ag in addr_groups if ag.resolved_members and ag.resolved_members != '[]']
                                    if addr_groups_with_members:
                                        addr_group = addr_groups_with_members[0]
                                    elif addr_groups:
                                        addr_group = addr_groups[0]

                                if addr_group:
                                    logger.debug(f"DEBUG NAT: Found address group '{addr}' with resolved_members: {addr_group.resolved_members}")

                                    # COMPREHENSIVE FIX: Prevent source address group expansion
                                    # This is the root cause of 1636+ false FQDN results

                                    # Step 1: Blacklist known source address group patterns
                                    source_group_blacklist = [
                                        'ext_',      # External source groups (ext_Office_NXG, ext_Office_XN, ext_PCH_*, etc.)
                                        'int_',      # Internal source groups
                                        'Office',    # Office address groups
                                        'CSP',       # CSP groups
                                        'AWS',       # Cloud provider groups
                                        'Google',    # Google Cloud groups
                                        'Azure',     # Azure groups
                                        'PCH_',      # PCH groups (can have 500+ members!)
                                        'PGW_',      # Payment gateway groups
                                        'LiveTVP_',  # Live TV groups
                                    ]

                                    is_source_group = any(addr.startswith(prefix) for prefix in source_group_blacklist)

                                    if is_source_group:
                                        logger.debug(f"DEBUG NAT: SKIPPING blacklisted source group '{addr}'")
                                        continue  # Skip this address entirely

                                    # Step 2: Whitelist ONLY VS-related objects
                                    is_vs_object = (
                                        addr.startswith('pub_') or      # Public IP objects (pub_203.0.113.36_32)
                                        addr.startswith('u-vs') or      # Virtual server objects
                                        addr.startswith('u_vs') or      # Alternative VS naming
                                        addr.startswith('vs') or        # Simple VS naming (vs21011_*)
                                        addr.startswith('i-vs') or      # Internal VS naming
                                        addr.startswith('p-vs')         # Production VS naming
                                    )

                                    # Step 3: Additional safety - limit member count
                                    try:
                                        members = json.loads(addr_group.resolved_members) if addr_group.resolved_members else []
                                        member_count = len(members)

                                        # If group has >10 members, it's likely NOT a VS public IP object
                                        # VS objects typically have 1-3 public IPs max
                                        if member_count > 10:
                                            logger.debug(f"DEBUG NAT: SKIPPING large group '{addr}' ({member_count} members - likely not a VS object)")
                                            continue
                                    except Exception:
                                        members = []
                                        member_count = 0

                                    # Step 4: Only process if it's a VS object
                                    if is_vs_object:
                                        logger.debug(f"DEBUG NAT: Processing VS object '{addr}' ({member_count} members)")
                                        try:
                                            for member_ip in members:
                                                clean_member_ip = member_ip.split('/')[0]  # Remove CIDR
                                                logger.debug(f"DEBUG NAT: Adding public IP: {clean_member_ip}")
                                                mapped_ips.append(clean_member_ip)
                                                mapping_type = 'Destination NAT'
                                        except Exception as e:
                                            logger.debug(f"DEBUG NAT: Error parsing group {addr}: {e}")
                                    else:
                                        logger.debug(f"DEBUG NAT: SKIPPING non-VS group '{addr}' ({member_count} members)")
                                else:
                                    logger.debug(f"DEBUG NAT: Address group '{addr}' not found")
                    except Exception as e:
                        # Add error handling to see what's going wrong
                        pass

            # Resolve object names to IPs for any non-IP values
            resolved_ips = []
            for ip_str in mapped_ips:
                try:
                    # Try to parse as IP address first
                    ip_utils.ip_address(ip_str)
                    resolved_ips.append(ip_str)
                except Exception:
                    # If not an IP, try to resolve as object name
                    if '_32' in ip_str:  # Likely an object name like "172.16.0.57_32"
                        ip_part = ip_str.replace('_32', '').replace('_', '.')
                        try:
                            ip_utils.ip_address(ip_part)
                            resolved_ips.append(ip_part)
                        except Exception:
                            # Try to find in address objects
                            addr_obj = FirewallAddressObject.query.filter_by(name=ip_str).first()
                            if addr_obj and addr_obj.ip_address:
                                resolved_ips.append(addr_obj.ip_address)

            logger.debug(f"DEBUG NAT: resolved_ips for policy {policy.name}: {resolved_ips}")
            if resolved_ips:
                # Get config file info for environment identification
                config_file = policy.config_file
                environment = 'Unknown'
                if config_file and config_file.filename:
                    if 'UAT' in config_file.filename.upper():
                        environment = 'UAT FW'
                    elif 'ADMIN' in config_file.filename.upper():
                        environment = 'Delta ADMIN FW'
                    else:
                        environment = config_file.filename

                nat_mappings.append({
                    'policy_id': policy.policy_id,
                    'policy_name': policy.name,
                    'environment': environment,
                    'source_zone': policy.source_zone,
                    'destination_zone': policy.destination_zone,
                    'private_ip': private_ip,
                    'mapped_public_ips': resolved_ips,
                    'mapping_type': mapping_type,
                    'source_translation': source_translation,
                    'destination_translation': destination_translation,
                    'status': policy.status
                })
                logger.debug(f"DEBUG NAT: Added mapping for policy {policy.name} with {len(resolved_ips)} public IPs")

        return {
            'success': True,
            'mappings': nat_mappings,
            'count': len(nat_mappings)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'mappings': [],
            'count': 0
        }

def get_fqdn_for_public_ips(public_ips):
    """Get FQDN records for a list of public IP addresses using BATCHED query for performance"""
    if not public_ips:
        return {'success': True, 'fqdn_mappings': [], 'count': 0}

    try:
        # PERFORMANCE OPTIMIZATION: Batch query all IPs in a single database connection
        # instead of making separate connections for each IP (which caused 90+ second timeouts)
        import pymysql

        connection = fqdn_db_connection()
        cursor = connection.cursor()

        # Build a single query with IN clause for all IPs
        # Use parameterized query to prevent SQL injection
        placeholders = ', '.join(['%s'] * len(public_ips))
        query = f"""
            SELECT id, owner, domain, fqdn, ttl, type_, ip, geoInfo
            FROM fqdn_new
            WHERE ip IN ({placeholders})
            ORDER BY ip, fqdn
        """

        cursor.execute(query, tuple(public_ips))
        results = cursor.fetchall()

        # Group results by IP
        ip_to_records = {}
        for row in results:
            ip_address = row[6]
            if ip_address not in ip_to_records:
                ip_to_records[ip_address] = []

            ip_to_records[ip_address].append({
                'id': row[0],
                'owner': row[1],
                'domain': row[2],
                'fqdn': row[3],
                'ttl': row[4],
                'type': row[5],
                'ip': row[6],
                'geo_info': row[7]
            })

        connection.close()

        # Build response matching original format
        all_fqdn_mappings = []
        for public_ip in public_ips:
            if public_ip in ip_to_records:
                all_fqdn_mappings.append({
                    'public_ip': public_ip,
                    'fqdn_records': ip_to_records[public_ip]
                })

        return {
            'success': True,
            'fqdn_mappings': all_fqdn_mappings,
            'count': len(all_fqdn_mappings)
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'fqdn_mappings': [],
            'count': 0
        }

@search_bp.route('/fqdn', methods=['POST'])
def search_fqdn():
    """Search for FQDN records in external database"""
    try:
        data = request.get_json()
        search_term = data.get('search_term', '').strip()
        infrastructure_filter = data.get('infrastructure_filter', None)
        
        # Remove trailing dots from FQDN search
        search_term = search_term.rstrip('.')
        
        if not search_term:
            return jsonify({
                'success': False,
                'message': 'Search term is required'
            }), 400
        
        if len(search_term) < 3:
            return jsonify({
                'success': False,
                'message': 'Search term must be at least 3 characters long'
            }), 400
        
        # Query the FQDN database
        fqdn_results = query_fqdn_database(search_term)

        if not fqdn_results['success']:
            return jsonify({
                'success': False,
                'message': f'FQDN search failed: {fqdn_results["error"]}'
            }), 500

        # Check if search term is an IP address and find NAT translations
        mapped_fqdn_results = {'success': True, 'fqdn_mappings': [], 'count': 0}
        try:
            import ipaddress as ip_utils
            ip_utils.ip_address(search_term)  # Will raise exception if not valid IP

            # Search for NAT translations for this IP
            nat_translation_results = find_nat_translations(search_term, infrastructure_filter)

            if nat_translation_results['success'] and nat_translation_results['mappings']:
                # Don't show any FQDN results for NAT translations where we searched for the private IP
                # Users typically only want FQDN results when searching for public IPs
                logger.debug(f"DEBUG FQDN: Excluding all NAT-mapped FQDN results when searching for private IP: {search_term}")
                logger.debug(f"DEBUG FQDN: Found {len(nat_translation_results['mappings'])} NAT mappings but not showing FQDN results for private IP searches")
        except ValueError:
            # search_term is not an IP address, skip NAT translation
            pass
        
        # Save search history (per user)
        user_id = request.headers.get('X-User-ID', 'anonymous')
        search_history = SearchHistory(
            user_id=user_id,
            search_query=search_term,
            search_type='fqdn',
            results_count=fqdn_results['count']
        )
        db.session.add(search_history)
        db.session.commit()
        
        # Extract IP addresses from FQDN results for further firewall and LTM analysis
        resolved_ips = set()
        if fqdn_results['success'] and fqdn_results['records']:
            for record in fqdn_results['records']:
                if record.get('ip') and record['type'] == 'A':
                    # Only include A records (not CNAME)
                    ip = record['ip'].strip()
                    try:
                        ipaddress.ip_address(ip)  # Validate IP
                        resolved_ips.add(ip)
                    except ValueError:
                        pass  # Skip invalid IPs

        # Initialize results for resolved IPs
        ltm_results_for_ips = {}
        firewall_results_for_ips = {}
        nat_results_for_ips = {}

        # Search LTM and Firewall configurations for each resolved IP
        if resolved_ips:

            for ip in resolved_ips:
                # Search LTM configurations
                ltm_result = search_ltm_configs(ip, 'both', infrastructure_filter)
                if ltm_result and (ltm_result.get('virtual_servers') or ltm_result.get('pools') or ltm_result.get('nodes')):
                    ltm_results_for_ips[ip] = ltm_result
                else:
                    # Create placeholder entry for IPs with no direct LTM results
                    ltm_results_for_ips[ip] = {
                        'success': True,
                        'virtual_servers': [],
                        'pools': [],
                        'nodes': []
                    }

                # Search firewall configurations
                firewall_result = search_firewall_configs(ip, 'both', 1, 1000, infrastructure_filter)
                if firewall_result and (firewall_result.get('policies') or firewall_result.get('address_objects')):
                    firewall_results_for_ips[ip] = firewall_result

                # Search NAT policies
                nat_result = find_nat_translations(ip, infrastructure_filter)
                if nat_result and nat_result.get('success') and nat_result.get('mappings'):
                    nat_results_for_ips[ip] = nat_result

        # Calculate total matches including both direct FQDN and mapped FQDN results
        total_fqdn_matches = fqdn_results['count'] + mapped_fqdn_results['count']

        # Extract virtual server references from firewall results and search LTM
        all_vs_references = set()
        for ip, fw_result in firewall_results_for_ips.items():
            vs_references = extract_vs_references_from_firewall_results(fw_result)
            all_vs_references.update(vs_references)

        # Search for additional LTM results using VS references
        if all_vs_references:
            ltm_cross_references = search_ltm_by_translated_ips(all_vs_references)

            # Check if we have actual virtual servers or pools in the results
            has_virtual_servers = ltm_cross_references and ltm_cross_references.get('virtual_servers')
            has_pools = ltm_cross_references and ltm_cross_references.get('pools_and_nodes')

            if has_virtual_servers or has_pools:
                # Merge cross-referenced results with existing LTM results for each IP
                for ip in ltm_results_for_ips:
                    ltm_results_for_ips[ip] = merge_ltm_results(ltm_results_for_ips[ip], ltm_cross_references)

        # ENHANCED: Query slbs table using FQDN pattern matching (like fqdn_compare)
        # This catches Virtual Servers that use naming conventions but don't have direct IP matches
        slbs_ltm_results = query_slbs_by_fqdn_pattern(search_term, infrastructure_filter)

        # Add slbs results to the ltm_results_for_ips under a special key
        if slbs_ltm_results.get('success') and slbs_ltm_results.get('virtual_servers'):
            # Store slbs results under 'slbs_pattern_match' key to distinguish from IP-based results
            ltm_results_for_ips['slbs_pattern_match'] = {
                'success': True,
                'virtual_servers': slbs_ltm_results['virtual_servers'],
                'pools': [],
                'nodes': [],
                'source': 'slbs',
                'patterns_used': slbs_ltm_results.get('patterns_used', [])
            }
            logger.debug(f"DEBUG FQDN: Found {len(slbs_ltm_results['virtual_servers'])} VS from slbs table using patterns: {slbs_ltm_results.get('patterns_used')}")

        total_firewall_matches = sum(len(result.get('policies', [])) for result in firewall_results_for_ips.values())
        total_nat_matches = sum(len(result.get('mappings', [])) for result in nat_results_for_ips.values())

        # Create flattened results for frontend compatibility
        flattened_firewall_results = {
            'success': True,
            'policies': [],
            'address_objects': [],
            'address_groups': [],
            'nat_policies': []
        }

        flattened_ltm_results = {
            'success': True,
            'virtual_servers': [],
            'pools': [],
            'nodes': []
        }

        # Flatten firewall results (including NAT policies)
        for ip, fw_result in firewall_results_for_ips.items():
            if fw_result.get('policies'):
                flattened_firewall_results['policies'].extend(fw_result['policies'])
            if fw_result.get('address_objects'):
                flattened_firewall_results['address_objects'].extend(fw_result['address_objects'])
            if fw_result.get('address_groups'):
                flattened_firewall_results['address_groups'].extend(fw_result['address_groups'])
            if fw_result.get('nat_policies'):
                flattened_firewall_results['nat_policies'].extend(fw_result['nat_policies'])

        # Also flatten any additional NAT results from find_nat_translations (if any)
        for ip, nat_result in nat_results_for_ips.items():
            if nat_result.get('mappings'):
                # NAT result mappings are the actual NAT policy objects
                flattened_firewall_results['nat_policies'].extend(nat_result['mappings'])

        # Flatten LTM results with proper deduplication
        unique_virtual_servers = {}
        unique_pools = {}
        unique_nodes = {}

        for ip, ltm_result in ltm_results_for_ips.items():
            if ltm_result.get('virtual_servers'):
                for vs_data in ltm_result['virtual_servers']:
                    vs = vs_data['virtual_server']
                    # Clean and normalize the key components
                    name = str(vs.get('name', '')).strip()
                    dest_ip = str(vs.get('destination_ip', '')).strip()
                    dest_port = str(vs.get('destination_port', '')).strip()

                    key = f"{name}_{dest_ip}_{dest_port}"
                    unique_virtual_servers[key] = vs_data

            if ltm_result.get('pools'):
                for pool_data in ltm_result['pools']:
                    pool_name = str(pool_data.get('name', '')).strip()
                    if pool_name and pool_name not in unique_pools:
                        unique_pools[pool_name] = pool_data

            if ltm_result.get('nodes'):
                for node_data in ltm_result['nodes']:
                    node_key = f"{node_data.get('ip_address', '')}:{node_data.get('port', '')}"
                    if node_key not in unique_nodes:
                        unique_nodes[node_key] = node_data

        # Convert back to lists
        flattened_ltm_results['virtual_servers'] = list(unique_virtual_servers.values())
        flattened_ltm_results['pools'] = list(unique_pools.values())
        flattened_ltm_results['nodes'] = list(unique_nodes.values())

        # Calculate total configuration matches using flattened (deduplicated) results
        total_ltm_matches = (len(flattened_ltm_results['virtual_servers']) +
                           len(flattened_ltm_results['pools']) +
                           len(flattened_ltm_results['nodes']))

        return jsonify({
            'success': True,
            'search_term': search_term,
            'search_type': 'fqdn_enhanced',
            'fqdn_results': fqdn_results,
            'mapped_fqdn_results': mapped_fqdn_results,
            'resolved_ips': list(resolved_ips),
            # Enhanced structure for future use
            'ltm_results_for_ips': ltm_results_for_ips,
            'firewall_results_for_ips': firewall_results_for_ips,
            'nat_results_for_ips': nat_results_for_ips,
            # Flattened structure for frontend compatibility
            'firewall_results': flattened_firewall_results,
            'ltm_results': flattened_ltm_results,
            'summary': {
                'fqdn_matches': fqdn_results['count'],
                'mapped_fqdn_matches': mapped_fqdn_results['count'],
                'total_fqdn_matches': total_fqdn_matches,
                'ltm_matches': total_ltm_matches,
                'firewall_matches': total_firewall_matches,
                'nat_matches': total_nat_matches,
                'total_matches': total_fqdn_matches + total_ltm_matches + total_firewall_matches + total_nat_matches
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'FQDN search failed: {str(e)}'
        }), 500

def classify_ip_address(ip_address, ltm_results):
    """Classify whether the searched IP address is a Virtual Server IP or Node IP"""
    classification = {
        'type': 'unknown',  # 'virtual_server', 'node', or 'unknown'
        'description': '',
        'details': []
    }
    
    # Check if the IP is a Virtual Server IP
    vs_matches = []
    for vs_data in ltm_results.get('virtual_servers', []):
        vs = vs_data['virtual_server']
        # Clean the destination IP by removing F5 path prefixes
        vs_ip = (vs['destination_ip'] or '').replace('/Common/', '').strip()
        if vs_ip == ip_address:
            vs_matches.append({
                'name': vs['name'],
                'destination_ip': vs['destination_ip'],
                'destination_port': vs['destination_port'],
                'pool_name': vs.get('pool_name', 'N/A')
            })
    
    # Check if the IP is a Node IP
    node_matches = []
    for vs_data in ltm_results.get('virtual_servers', []):
        vs = vs_data['virtual_server']
        for node in vs_data.get('pool_nodes', []):
            if node['ip_address'] == ip_address:
                node_matches.append({
                    'virtual_server': vs['name'],
                    'pool_name': vs.get('pool_name', 'N/A'),
                    'node_ip': node['ip_address'],
                    'node_port': node['port'],
                    'vs_destination': f"{vs['destination_ip']}:{vs['destination_port']}"
                })
    
    # Determine classification based on matches
    if vs_matches:
        classification['type'] = 'virtual_server'
        classification['description'] = 'Virtual Server IP'
        classification['details'] = vs_matches
    elif node_matches:
        classification['type'] = 'node'
        classification['description'] = 'Node IP'  
        classification['details'] = node_matches
    else:
        classification['type'] = 'unknown'
        classification['description'] = 'No LTM matches found'
        classification['details'] = []
    
    return classification

@search_bp.route('/ip', methods=['POST'])
def search_ip():
    """Search for IP address across all configurations"""
    try:
        data = request.get_json()
        ip_address = data.get('ip_address', '').strip()
        search_direction = data.get('search_direction', 'both')  # 'both', 'source', 'destination'
        infrastructure_filter = data.get('infrastructure_filter', None)
        
        if not ip_address:
            return jsonify({
                'success': False,
                'message': 'IP address is required'
            }), 400
        
        # Check if input is an object name (not an IP address)
        is_object_name = False
        object_resolved_ips = []
        object_fqdn_results = {'success': True, 'records': [], 'count': 0, 'sections': {}}

        # Validate IP address format (support partial IPs)
        if not is_partial_ip(ip_address):
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                # If it's not a valid IP, treat it as an object name
                is_object_name = True

                # Try to resolve object name to IP(s)
                resolution_result = resolve_object_to_ip(ip_address, infrastructure_filter)
                if resolution_result['success'] and resolution_result['resolved_ips']:
                    object_resolved_ips = resolution_result['resolved_ips']

                    # Get FQDN results for the resolved IPs, organized by IP
                    # First deduplicate resolved IPs (clean up any /Common/ prefixes)
                    unique_ips = set()
                    for resolved_ip in object_resolved_ips:
                        clean_ip = resolved_ip.replace('/Common/', '')
                        unique_ips.add(clean_ip)

                    for clean_ip in unique_ips:
                        fqdn_result = query_fqdn_database(clean_ip)
                        if fqdn_result['success'] and fqdn_result['records']:
                            # Add to sections organized by IP
                            if clean_ip not in object_fqdn_results['sections']:
                                object_fqdn_results['sections'][clean_ip] = {
                                    'ip': clean_ip,
                                    'records': [],
                                    'count': 0
                                }

                            object_fqdn_results['sections'][clean_ip]['records'].extend(fqdn_result['records'])
                            object_fqdn_results['sections'][clean_ip]['count'] = len(object_fqdn_results['sections'][clean_ip]['records'])

                    # Build the main records list from sections to avoid duplicates
                    all_records = []
                    for section in object_fqdn_results['sections'].values():
                        all_records.extend(section['records'])
                    object_fqdn_results['records'] = all_records
                    object_fqdn_results['count'] = len(all_records)

                # If we can't resolve it to any IPs, continue with regular search
                # in case it's a partial match for other objects
        
        # Get pagination parameters
        page = data.get('page', 1)
        page_size = data.get('page_size', 1000)

        # Execute searches in parallel with proper Flask context
        @copy_current_request_context
        def search_ltm_with_context():
            return search_ltm_configs(ip_address, search_direction, infrastructure_filter)

        @copy_current_request_context
        def search_firewall_with_context():
            return search_firewall_configs(ip_address, search_direction, page, page_size, infrastructure_filter)

        @copy_current_request_context
        def search_fqdn_with_context():
            return query_fqdn_database(ip_address)

        @copy_current_request_context
        def search_nat_with_context():
            return find_nat_translations(ip_address, None)

        # Execute all searches in parallel for much better performance
        import time
        start_time = time.time()
        logger.info(f"Starting parallel search for IP: {ip_address}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all tasks
            ltm_future = executor.submit(search_ltm_with_context)
            firewall_future = executor.submit(search_firewall_with_context)
            fqdn_future = executor.submit(search_fqdn_with_context)
            nat_future = executor.submit(search_nat_with_context)

            # Wait for all results using as_completed for better performance tracking
            futures = {
                'ltm': ltm_future,
                'firewall': firewall_future,
                'fqdn': fqdn_future,
                'nat': nat_future
            }

            results = {}
            for future_name, future in futures.items():
                future_start = time.time()
                try:
                    results[future_name] = future.result(timeout=30)  # 30 second timeout per operation
                    logger.info(f"{future_name} search completed in {time.time() - future_start:.2f} seconds")
                except Exception as e:
                    logger.warning(f"{future_name} search failed: {str(e)}")
                    results[future_name] = {'success': False, 'error': str(e)}

            ltm_results = results.get('ltm', {'success': False, 'virtual_servers': []})
            firewall_results = results.get('firewall', {'success': False, 'policies': []})
            fqdn_results = results.get('fqdn', {'success': False, 'fqdn_mappings': []})
            nat_translation_results = results.get('nat', {'success': False, 'mappings': []})

            logger.info(f"All parallel searches completed in {time.time() - start_time:.2f} seconds")

        # Extract virtual server references from firewall policies and search for them in LTM
        vs_references = extract_vs_references_from_firewall_results(firewall_results)
        if vs_references:
            ltm_cross_references = search_ltm_by_translated_ips(vs_references)
            # Merge cross-referenced results with existing LTM results
            ltm_results = merge_ltm_results(ltm_results, ltm_cross_references)

        # Don't show FQDN results for NAT translations when searching for private IPs
        # Users typically only want FQDN results when searching for public IPs
        mapped_fqdn_results = {'success': True, 'fqdn_mappings': [], 'count': 0}
        if nat_translation_results['success'] and nat_translation_results['mappings']:
            logger.debug(f"DEBUG SEARCH: Excluding all NAT-mapped FQDN results when searching for private IP: {ip_address}")
            logger.debug(f"DEBUG SEARCH: Found {len(nat_translation_results['mappings'])} NAT mappings but not showing FQDN results for private IP searches")

        # Check if this IP is a pool member and find its virtual servers to get FQDN results
        vs_mapping_results = {'success': True, 'virtual_servers': [], 'vs_fqdn_results': {'success': True, 'records': [], 'count': 0}, 'count': 0}
        if not is_object_name:  # Only do this for actual IP addresses, not object names
            try:
                # Parse the IP to ensure it's a valid IP address before searching
                ipaddress.ip_address(ip_address)
                vs_mapping_results = find_vs_for_pool_member(ip_address, infrastructure_filter)
            except ValueError:
                # Not a valid IP address, skip VS mapping
                pass

        # Classify the IP address (Virtual Server IP vs Node IP)
        ip_classification = classify_ip_address(ip_address, ltm_results)
        
        # Count total matches
        ltm_count = len(ltm_results['virtual_servers']) + len(ltm_results['pools_and_nodes'])
        firewall_count = len(firewall_results['address_objects']) + len(firewall_results['policies']) + len(firewall_results['nat_policies'])
        fqdn_count = fqdn_results['count'] if fqdn_results['success'] else 0
        nat_mapping_count = nat_translation_results['count'] if nat_translation_results['success'] else 0
        mapped_fqdn_count = mapped_fqdn_results['count'] if mapped_fqdn_results['success'] else 0
        object_fqdn_count = object_fqdn_results['count'] if object_fqdn_results['success'] else 0
        vs_mapping_fqdn_count = vs_mapping_results['vs_fqdn_results']['count'] if vs_mapping_results['success'] else 0

        # Save search history (per user)
        user_id = request.headers.get('X-User-ID', 'anonymous')
        search_history = SearchHistory(
            user_id=user_id,
            search_query=ip_address,
            search_type='ip',
            results_count=ltm_count + firewall_count + fqdn_count + nat_mapping_count + mapped_fqdn_count + object_fqdn_count + vs_mapping_fqdn_count
        )
        db.session.add(search_history)
        db.session.commit()

        response_data = {
            'success': True,
            'ip_address': ip_address,
            'ip_classification': ip_classification,
            'ltm_results': ltm_results,
            'firewall_results': firewall_results,
            'fqdn_results': fqdn_results,
            'nat_translation_results': nat_translation_results,
            'mapped_fqdn_results': mapped_fqdn_results,
            'summary': {
                'ltm_matches': ltm_count,
                'firewall_matches': firewall_count,
                'fqdn_matches': fqdn_count,
                'nat_mappings': nat_mapping_count,
                'mapped_fqdn_matches': mapped_fqdn_count,
                'total_matches': ltm_count + firewall_count + fqdn_count + nat_mapping_count + mapped_fqdn_count + object_fqdn_count + vs_mapping_fqdn_count,
                'address_objects': len(firewall_results['address_objects']),
                'policies': len(firewall_results['policies']),
                'nat_policies': len(firewall_results['nat_policies'])
            }
        }

        # Add object resolution results if it was an object name search
        if is_object_name and object_resolved_ips:
            response_data['object_resolution'] = {
                'success': True,
                'resolved_ips': object_resolved_ips,
                'fqdn_results': object_fqdn_results
            }
            response_data['summary']['object_fqdn_matches'] = object_fqdn_count

        # Add VS mapping results if virtual servers were found for this pool member IP
        if vs_mapping_results['success'] and vs_mapping_results['count'] > 0:
            response_data['vs_mapping'] = vs_mapping_results
            response_data['summary']['vs_mapping_fqdn_matches'] = vs_mapping_fqdn_count

        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Search failed: {str(e)}'
        }), 500


@search_bp.route('/bulk_ip', methods=['POST'])
def search_bulk_ip():
    """Search for multiple IP addresses across all configurations"""
    try:
        data = request.get_json()
        ip_addresses = data.get('ip_addresses', [])
        search_direction = data.get('search_direction', 'both')  # 'both', 'source', 'destination'
        infrastructure_filter = data.get('infrastructure_filter', None)
        
        if not ip_addresses:
            return jsonify({
                'success': False,
                'message': 'At least one IP address is required'
            }), 400
        
        # Validate all IP addresses
        validated_ips = []
        for ip in ip_addresses:
            ip = ip.strip()
            if not ip:
                continue
            # Validate IP address (support partial IPs)
            if not is_partial_ip(ip):
                try:
                    ipaddress.ip_address(ip)
                    validated_ips.append(ip)
                except ValueError:
                    return jsonify({
                        'success': False,
                        'message': f'Invalid IP address format: {ip}'
                    }), 400
            else:
                validated_ips.append(ip)  # Add partial IP to validated list
        
        if not validated_ips:
            return jsonify({
                'success': False,
                'message': 'No valid IP addresses provided'
            }), 400
        
        # Search each IP and collect results
        all_results = {}
        total_ltm_count = 0
        total_firewall_count = 0
        total_fqdn_count = 0
        
        for ip_address in validated_ips:
            # Search LTM configurations
            ltm_results = search_ltm_configs(ip_address, search_direction, infrastructure_filter)

            # Search firewall configurations (use default pagination for bulk search)
            firewall_results = search_firewall_configs(ip_address, search_direction, 1, 50, infrastructure_filter)
            
            # Extract virtual server references from firewall policies and search for them in LTM
            vs_references = extract_vs_references_from_firewall_results(firewall_results)
            if vs_references:
                ltm_cross_references = search_ltm_by_translated_ips(vs_references)
                # Merge cross-referenced results with existing LTM results
                ltm_results = merge_ltm_results(ltm_results, ltm_cross_references)
            
            # Search FQDN database
            fqdn_results = query_fqdn_database(ip_address)
            
            # Classify the IP address
            ip_classification = classify_ip_address(ip_address, ltm_results)
            
            # Count matches for this IP
            ltm_count = len(ltm_results['virtual_servers']) + len(ltm_results['pools_and_nodes'])
            firewall_count = len(firewall_results['address_objects']) + len(firewall_results['policies']) + len(firewall_results['nat_policies'])
            fqdn_count = fqdn_results['count'] if fqdn_results['success'] else 0
            
            total_ltm_count += ltm_count
            total_firewall_count += firewall_count
            total_fqdn_count += fqdn_count
            
            # Store results for this IP
            all_results[ip_address] = {
                'ip_classification': ip_classification,
                'ltm_results': ltm_results,
                'firewall_results': firewall_results,
                'fqdn_results': fqdn_results,
                'summary': {
                    'ltm_matches': ltm_count,
                    'firewall_matches': firewall_count,
                    'fqdn_matches': fqdn_count,
                    'total_matches': ltm_count + firewall_count + fqdn_count,
                    'address_objects': len(firewall_results['address_objects']),
                    'policies': len(firewall_results['policies']),
                    'nat_policies': len(firewall_results['nat_policies'])
                }
            }
            
            # Save search history for each IP (per user)
            user_id = request.headers.get('X-User-ID', 'anonymous')
            search_history = SearchHistory(
                user_id=user_id,
                search_query=ip_address,
                search_type='ip',
                results_count=ltm_count + firewall_count + fqdn_count
            )
            db.session.add(search_history)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'bulk_results': all_results,
            'summary': {
                'searched_ips': len(validated_ips),
                'total_ltm_matches': total_ltm_count,
                'total_firewall_matches': total_firewall_count,
                'total_fqdn_matches': total_fqdn_count,
                'total_matches': total_ltm_count + total_firewall_count + total_fqdn_count
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Bulk search failed: {str(e)}'
        }), 500


@search_bp.route('/object', methods=['POST'])
def search_object():
    """Search for object name across all configurations"""
    import time
    start_time = time.time()
    
    try:
        data = request.get_json()
        object_name = data.get('object_name', '').strip()
        infrastructure_filter = data.get('infrastructure_filter', None)
        
        if not object_name:
            return jsonify({
                'success': False,
                'message': 'Object name is required'
            }), 400
        
        if len(object_name) < 3:
            return jsonify({
                'success': False,
                'message': 'Object name must be at least 3 characters long for performance reasons'
            }), 400
        
        # Search LTM configurations with timeout check
        ltm_results = search_ltm_objects(object_name, infrastructure_filter)

        # Check if we're taking too long
        if time.time() - start_time > 60:  # 60 second timeout
            return jsonify({
                'success': False,
                'message': 'Search taking too long, please try a more specific search term'
            }), 408

        # Search firewall configurations with timeout check
        firewall_results = search_firewall_objects(object_name, infrastructure_filter)

        # Don't search FQDN database with object name directly (causes false positives)
        # FQDN search will happen via NAT public IP lookup below
        fqdn_results = {'success': True, 'records': [], 'count': 0}

        # PERFORMANCE OPTIMIZATION: Skip object FQDN resolution for object searches
        # Object searches are primarily for finding firewall policies and LTM virtual servers
        # FQDN results are most useful for specific IP searches and VS NAT mappings
        # Skipping this improves performance dramatically for large objects (e.g., vs28000_TapTap_MEM with 1200+ IPs)
        object_resolved_ips = []
        object_fqdn_results = {
            'success': True,
            'records': [],
            'count': 0,
            'sections': {},
            'skipped': True,
            'message': 'FQDN lookup skipped for object searches to improve performance'
        }
        logger.debug(f"DEBUG OBJECT SEARCH: Skipping object FQDN resolution for '{object_name}' to improve performance")

        # Check VS IPs from LTM results for NAT mapping and FQDN lookup
        # PERFORMANCE OPTIMIZATION: Skip VS NAT FQDN lookups for searches with many VSs to avoid timeout
        MAX_VS_FOR_NAT_FQDN = 3  # Only do expensive NAT/FQDN lookups for 3 or fewer VSs
        vs_nat_fqdn_results = {'success': True, 'vs_mappings': [], 'count': 0, 'skipped': False}

        if ltm_results['virtual_servers'] and len(ltm_results['virtual_servers']) <= MAX_VS_FOR_NAT_FQDN:
            try:
                import time
                vs_nat_start = time.time()
                logger.debug(f"DEBUG VS NAT: Processing {len(ltm_results['virtual_servers'])} virtual servers for NAT/FQDN lookup")

                # PERFORMANCE OPTIMIZATION: Batch collect all VS IPs and public IPs before FQDN lookup
                # Instead of individual FQDN query per VS, collect all public IPs then query once
                all_vs_data = []  # Store VS info for later processing
                all_public_ips = set()  # Collect all public IPs from all VSs

                for vs_index, vs in enumerate(ltm_results['virtual_servers']):
                    if vs.get('virtual_server') and vs['virtual_server'].get('destination_ip'):
                        vs_ip = vs['virtual_server']['destination_ip']
                        vs_name = vs['virtual_server']['name']
                        vs_start = time.time()
                        logger.debug(f"DEBUG VS NAT [{vs_index+1}/{len(ltm_results['virtual_servers'])}]: Checking VS '{vs_name}' with IP '{vs_ip}'")

                        # Check NAT mapping for this VS IP
                        nat_start = time.time()
                        nat_result = find_nat_translations(vs_ip, infrastructure_filter)
                        nat_elapsed = time.time() - nat_start
                        logger.debug(f"DEBUG VS NAT: NAT lookup took {nat_elapsed:.2f}s for '{vs_name}'")
                        if nat_result['success'] and nat_result['mappings']:
                            # Collect all public IPs from NAT mappings
                            public_ips = set()
                            for mapping in nat_result['mappings']:
                                public_ips.update(mapping.get('mapped_public_ips', []))

                            if public_ips:
                                logger.debug(f"DEBUG VS NAT: Found {len(public_ips)} public IPs for VS '{vs_name}': {list(public_ips)}")

                                # OPTIMIZATION: Collect public IPs for batched FQDN lookup instead of individual queries
                                all_public_ips.update(public_ips)
                                all_vs_data.append({
                                    'vs_name': vs_name,
                                    'vs_ip': vs_ip,
                                    'nat_mappings': nat_result['mappings'],
                                    'public_ips': list(public_ips)
                                })

                        vs_elapsed = time.time() - vs_start
                        logger.debug(f"DEBUG VS NAT: Total time for VS '{vs_name}': {vs_elapsed:.2f}s")

                # BATCHED FQDN LOOKUP: Query all public IPs in one call instead of per-VS
                logger.debug(f"DEBUG VS NAT: Collected {len(all_public_ips)} unique public IPs from all VSs")
                if all_public_ips:
                    fqdn_batch_start = time.time()
                    all_fqdn_results = get_fqdn_for_public_ips(list(all_public_ips))
                    fqdn_batch_elapsed = time.time() - fqdn_batch_start
                    logger.debug(f"DEBUG VS NAT: Batched FQDN lookup took {fqdn_batch_elapsed:.2f}s for {len(all_public_ips)} IPs")

                    # Build IP-to-FQDN mapping for quick lookup
                    ip_to_fqdn = {}
                    if all_fqdn_results['success'] and all_fqdn_results['fqdn_mappings']:
                        for mapping in all_fqdn_results['fqdn_mappings']:
                            ip_to_fqdn[mapping['public_ip']] = mapping['fqdn_records']

                    # Now match FQDNs back to each VS
                    for vs_data in all_vs_data:
                        vs_fqdn_mappings = []
                        for public_ip in vs_data['public_ips']:
                            if public_ip in ip_to_fqdn:
                                vs_fqdn_mappings.append({
                                    'public_ip': public_ip,
                                    'fqdn_records': ip_to_fqdn[public_ip]
                                })

                        if vs_fqdn_mappings:
                            vs_nat_fqdn_results['vs_mappings'].append({
                                'vs_name': vs_data['vs_name'],
                                'vs_ip': vs_data['vs_ip'],
                                'nat_mappings': vs_data['nat_mappings'],
                                'public_ips': vs_data['public_ips'],
                                'fqdn_mappings': vs_fqdn_mappings
                            })

                vs_nat_fqdn_results['count'] = len(vs_nat_fqdn_results['vs_mappings'])
                vs_nat_total = time.time() - vs_nat_start
                logger.debug(f"DEBUG VS NAT: Total VS with NAT/FQDN mappings: {vs_nat_fqdn_results['count']}")
                logger.debug(f"DEBUG VS NAT: TOTAL TIME for all VS NAT/FQDN lookups: {vs_nat_total:.2f}s")

            except Exception as e:
                logger.debug(f"DEBUG VS NAT: Error during VS NAT/FQDN lookup: {str(e)}")
                vs_nat_fqdn_results = {'success': False, 'error': str(e), 'vs_mappings': [], 'count': 0, 'skipped': False}
        elif ltm_results['virtual_servers']:
            # Too many VSs - skip expensive NAT/FQDN lookups to avoid timeout
            logger.debug(f"DEBUG VS NAT: Skipping VS NAT/FQDN lookup - too many VSs ({len(ltm_results['virtual_servers'])} > {MAX_VS_FOR_NAT_FQDN})")
            vs_nat_fqdn_results = {'success': True, 'vs_mappings': [], 'count': 0, 'skipped': True, 'reason': f'Too many virtual servers ({len(ltm_results["virtual_servers"])} > {MAX_VS_FOR_NAT_FQDN})'}

        # Count total matches
        ltm_count = len(ltm_results['virtual_servers']) + len(ltm_results['pools_and_nodes'])
        firewall_count = (len(firewall_results['address_objects']) +
                         len(firewall_results['address_groups']) +
                         len(firewall_results['policies']) +
                         len(firewall_results['nat_policies']))
        fqdn_count = fqdn_results['count'] if fqdn_results['success'] else 0
        object_fqdn_count = object_fqdn_results['count'] if object_fqdn_results['success'] else 0
        vs_nat_fqdn_count = vs_nat_fqdn_results['count'] if vs_nat_fqdn_results['success'] else 0
        
        # Save search history (per user)
        user_id = request.headers.get('X-User-ID', 'anonymous')
        search_history = SearchHistory(
            user_id=user_id,
            search_query=object_name,
            search_type='object',
            results_count=ltm_count + firewall_count + fqdn_count + object_fqdn_count + vs_nat_fqdn_count
        )
        db.session.add(search_history)
        db.session.commit()

        response_data = {
            'success': True,
            'object_name': object_name,
            'search_type': 'object',
            'ltm_results': ltm_results,
            'firewall_results': firewall_results,
            'fqdn_results': fqdn_results,
            'vs_nat_fqdn_results': vs_nat_fqdn_results,
            'summary': {
                'ltm_matches': ltm_count,
                'firewall_matches': firewall_count,
                'fqdn_matches': fqdn_count,
                'vs_nat_fqdn_matches': vs_nat_fqdn_count,
                'total_matches': ltm_count + firewall_count + fqdn_count + object_fqdn_count + vs_nat_fqdn_count,
                'address_objects': len(firewall_results['address_objects']),
                'address_groups': len(firewall_results['address_groups']),
                'policies': len(firewall_results['policies']),
                'nat_policies': len(firewall_results['nat_policies'])
            }
        }

        # Add object resolution results if IPs were resolved
        if object_resolved_ips:
            response_data['object_resolution'] = {
                'success': True,
                'resolved_ips': object_resolved_ips,
                'fqdn_results': object_fqdn_results
            }
            response_data['summary']['object_fqdn_matches'] = object_fqdn_count

        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Search failed: {str(e)}'
        }), 500

@search_bp.route('/history', methods=['GET'])
def get_search_history():
    """Get per-user search history"""
    try:
        user_id = request.headers.get('X-User-ID', 'anonymous')
        limit = request.args.get('limit', 20, type=int)

        history = SearchHistory.query.filter_by(user_id=user_id).order_by(
            SearchHistory.search_date.desc()
        ).limit(limit).all()

        return jsonify({
            'success': True,
            'history': [item.serialize for item in history]
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to get search history: {str(e)}'
        }), 500
        
        
@search_bp.route('/hostmonitor_keep_alive', methods=['GET'])
@search_bp.route('/hostmonitor_keep_alive/', methods=['GET'])
def hostmonitor_keep_alive():     
    
    return "1"   

@search_bp.route('/history/clear', methods=['POST'])
def clear_search_history():
    """Clear per-user search history"""
    try:
        user_id = request.headers.get('X-User-ID', 'anonymous')

        SearchHistory.query.filter_by(user_id=user_id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Search history cleared successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to clear search history: {str(e)}'
        }), 500