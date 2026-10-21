from parsers.ltm_parser import LtmConfigParser
from parsers.firewall_parser import FirewallConfigParser
from model import db, ConfigFile, FirewallAddressGroup, FirewallAddressObject
import json
import time
from datetime import datetime

def log(msg):
    """Print progress with timestamp, flush immediately for gunicorn"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

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
        ).limit(500).all()  # Limit to prevent memory issues
        
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

class ParserService:
    @staticmethod
    def parse_config_file(config_file_id):
        """Parse a configuration file and store results in database"""
        try:
            config_file = ConfigFile.query.get(config_file_id)
            if not config_file:
                return {'success': False, 'message': 'Config file not found'}
            
            # Read file content
            with open(config_file.file_path, 'r') as f:
                content = f.read()
            
            # Update status to parsing
            config_file.parsed_status = 'parsing'
            db.session.commit()
            
            # Parse based on file type
            if config_file.file_type == 'ltm':
                parser = LtmConfigParser(content, config_file_id)
                result = parser.parse()
                
            elif config_file.file_type in ['fw_prod', 'fw_admin', 'firewall']:
                parser = FirewallConfigParser(content, config_file_id)
                result = parser.parse()
            
            else:
                return {'success': False, 'message': f'Unknown file type: {config_file.file_type}'}
            
            # Update status to parsed
            config_file.parsed_status = 'parsed'
            db.session.commit()
            
            return {
                'success': True,
                'message': 'Config file parsed successfully',
                'result': result
            }
            
        except Exception as e:
            # Update status to error
            if 'config_file' in locals():
                config_file.parsed_status = 'error'
                db.session.commit()
            
            return {
                'success': False,
                'message': f'Parsing failed: {str(e)}'
            }
    
    @staticmethod
    def parse_all_pending():
        """Parse all pending configuration files"""
        pending_files = ConfigFile.query.filter_by(parsed_status='pending').all()
        results = []
        total = len(pending_files)

        for idx, config_file in enumerate(pending_files, 1):
            log(f"  Parsing [{idx}/{total}] {config_file.filename} ({config_file.file_type})")
            t = time.time()
            result = ParserService.parse_config_file(config_file.id)
            elapsed = time.time() - t
            status = "OK" if result.get('success') else "FAILED"
            log(f"    {status} in {elapsed:.1f}s")
            results.append({
                'file_id': config_file.id,
                'filename': config_file.filename,
                'file_type': config_file.file_type,
                'result': result
            })

        # After parsing all files, populate resolved members for firewall groups
        log("  Populating resolved members for firewall groups...")
        t = time.time()
        ParserService.populate_resolved_members()
        log(f"  Resolved members done in {time.time() - t:.1f}s")

        return results
    
    @staticmethod
    def populate_resolved_members():
        """Populate resolved_members and member_count for all firewall address groups"""
        try:
            # Get all firewall address groups that need resolved members populated
            all_groups = FirewallAddressGroup.query.all()

            if not all_groups:
                return {'success': True, 'message': 'No firewall groups found to process'}

            total = len(all_groups)
            log(f"    Processing {total} firewall address groups...")

            # Process in larger batches for speed
            updated_count = 0
            error_count = 0
            batch_size = 500

            for i in range(0, total, batch_size):
                batch_groups = all_groups[i:i+batch_size]

                for group in batch_groups:
                    if not group.members or not group.member_details:
                        continue

                    try:
                        # Parse member_details to get the actual IPs for THIS specific group
                        member_details = json.loads(group.member_details) if isinstance(group.member_details, str) else group.member_details

                        if not member_details:
                            continue

                        # Extract IPs directly from member_details
                        resolved_ips = []
                        for member in member_details:
                            if isinstance(member, dict):
                                ip = member.get('ip')
                                if ip and ip != 'N/A':
                                    resolved_ips.append(ip)

                        # Update this specific group
                        if resolved_ips:
                            group.resolved_members = json.dumps(resolved_ips)
                            group.member_count = len(resolved_ips)
                            updated_count += 1

                    except Exception as e:
                        error_count += 1
                        continue

                # Commit batch updates
                db.session.commit()

            log(f"    Resolved members: {updated_count}/{total} updated, {error_count} errors")
            return {
                'success': True,
                'message': f'Populated resolved members for {updated_count} firewall address groups'
            }

        except Exception as e:
            db.session.rollback()
            print(f"Error populating resolved members: {str(e)}")
            return {
                'success': False,
                'message': f'Failed to populate resolved members: {str(e)}'
            }