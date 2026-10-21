import re
import json
from model import db, LtmVirtualServer, LtmPool, LtmNode

class LtmConfigParser:
    def __init__(self, config_content, config_file_id):
        self.config_content = config_content
        self.config_file_id = config_file_id
        self.virtual_servers = []
        self.pools = []
        self.nodes = []
    
    def parse(self):
        """Parse LTM configuration and extract all components"""
        lines = self.config_content.split('\n')
        
        # Parse virtual servers
        self._parse_virtual_servers(lines)
        
        # Parse pools and commit to get IDs
        self._parse_pools(lines)
        db.session.commit()  # Commit pools to get their IDs
        
        # Parse nodes (needs pool IDs)
        self._parse_nodes(lines)
        db.session.commit()  # Commit all changes
        
        return {
            'virtual_servers': len(self.virtual_servers),
            'pools': len(self.pools),
            'nodes': len(self.nodes)
        }
    
    def _parse_virtual_servers(self, lines):
        """Extract virtual server configurations"""
        current_vs = None
        in_vs_block = False
        brace_count = 0
        
        for line in lines:
            line = line.strip()
            
            # Start of virtual server block
            vs_match = re.match(r'ltm virtual\s+(.+?)\s*{', line)
            if vs_match:
                vs_name = vs_match.group(1).strip()
                current_vs = {
                    'name': vs_name,
                    'destination_ip': None,
                    'destination_port': None,
                    'pool_name': None,
                    'status': None
                }
                in_vs_block = True
                brace_count = 1  # Count the opening brace
                continue
            
            # Track nested braces when in VS block
            if in_vs_block:
                # Count opening braces
                if '{' in line:
                    brace_count += line.count('{')
                # Count closing braces
                if '}' in line:
                    brace_count -= line.count('}')
                
                # End of virtual server block when brace count reaches 0
                if brace_count == 0:
                    if current_vs and current_vs['name']:
                        vs_obj = LtmVirtualServer(
                            config_file_id=self.config_file_id,
                            name=current_vs['name'],
                            destination_ip=current_vs['destination_ip'],
                            destination_port=int(current_vs['destination_port']) if current_vs['destination_port'] and current_vs['destination_port'].isdigit() else None,
                            pool_name=current_vs['pool_name'],
                            enabled=current_vs['status'] != 'disabled' if current_vs['status'] else True
                        )
                        self.virtual_servers.append(vs_obj)
                        db.session.add(vs_obj)
                    
                    current_vs = None
                    in_vs_block = False
                    brace_count = 0
                    continue
            
            # Parse properties within virtual server block
            if in_vs_block and current_vs:
                # Destination (IP:port) - only at top level (brace_count == 1)
                if brace_count == 1:
                    dest_match = re.match(r'destination\s+(.+)', line)
                    if dest_match:
                        destination = dest_match.group(1).strip()
                        # Split IP and port
                        if ':' in destination:
                            parts = destination.rsplit(':', 1)
                            current_vs['destination_ip'] = parts[0]
                            current_vs['destination_port'] = parts[1]
                        else:
                            current_vs['destination_ip'] = destination

                    # Pool - only at top level (brace_count == 1) to avoid SNAT pools
                    pool_match = re.match(r'pool\s+(.+)', line)
                    if pool_match:
                        pool_name = pool_match.group(1).strip()
                        # Treat "none" as no pool (NULL)
                        current_vs['pool_name'] = None if pool_name.lower() == 'none' else pool_name
                
                # Status
                if 'disabled' in line.lower():
                    current_vs['status'] = 'disabled'
                elif 'enabled' in line.lower():
                    current_vs['status'] = 'enabled'
    
    def _parse_pools(self, lines):
        """Extract pool configurations"""
        current_pool = None
        in_pool_block = False
        brace_count = 0
        
        for line in lines:
            line = line.strip()
            
            # Start of pool block
            pool_match = re.match(r'ltm pool\s+(.+?)\s*{', line)
            if pool_match:
                pool_name = pool_match.group(1).strip()
                current_pool = {
                    'name': pool_name,
                    'monitor': None,
                    'load_balancing_method': None
                }
                in_pool_block = True
                brace_count = 1  # Count the opening brace
                continue
            
            # Track nested braces when in pool block
            if in_pool_block:
                # Count opening braces
                if '{' in line:
                    brace_count += line.count('{')
                # Count closing braces
                if '}' in line:
                    brace_count -= line.count('}')
                
                # End of pool block when brace count reaches 0
                if brace_count == 0:
                    if current_pool and current_pool['name']:
                        pool_obj = LtmPool(
                            config_file_id=self.config_file_id,
                            name=current_pool['name'],
                            monitor=current_pool['monitor'],
                            load_balancing_method=current_pool['load_balancing_method']
                        )
                        self.pools.append(pool_obj)
                        db.session.add(pool_obj)
                    
                    current_pool = None
                    in_pool_block = False
                    brace_count = 0
                    continue
            
            # Parse properties within pool block
            if in_pool_block and current_pool:
                # Monitor
                monitor_match = re.match(r'monitor\s+(.+)', line)
                if monitor_match:
                    current_pool['monitor'] = monitor_match.group(1).strip()
                
                # Load balancing method
                lb_match = re.match(r'load-balancing-mode\s+(.+)', line)
                if lb_match:
                    current_pool['load_balancing_method'] = lb_match.group(1).strip()
    
    def _parse_nodes(self, lines):
        """Extract node configurations from pools"""
        current_pool_name = None
        in_pool_block = False
        in_members_block = False
        in_member_config = False
        members_brace_depth = 0
        current_member = None
        
        for line in lines:
            line = line.strip()
            
            # Start of pool block
            pool_match = re.match(r'ltm pool\s+(.+?)\s*{', line)
            if pool_match:
                current_pool_name = pool_match.group(1).strip()
                in_pool_block = True
                continue
            
            # End of pool block
            if in_pool_block and line == '}' and not in_members_block:
                current_pool_name = None
                in_pool_block = False
                continue
            
            # Members section
            if in_pool_block and 'members {' in line:
                in_members_block = True
                members_brace_depth = 1  # Start tracking brace depth
                continue
            
            # Track braces within members block
            if in_members_block:
                # Count opening braces
                members_brace_depth += line.count('{')
                # Count closing braces
                members_brace_depth -= line.count('}')
                
                # If brace depth reaches 0, we're out of the members block
                if members_brace_depth <= 0:
                    in_members_block = False
                    members_brace_depth = 0
                    current_member = None
                    in_member_config = False
                    continue
            
            # Parse member entries
            if in_members_block and current_pool_name:
                # Member format: /Common/IP:port { ... } or IP:port { ... }
                # Port can be a number or service name (http, https, etc.)
                member_match = re.match(r'/?(?:Common/)?([^/:]+):([^\s{]+)\s*{?', line)
                if member_match:
                    ip_address = member_match.group(1).strip()
                    port = member_match.group(2).strip()
                    
                    # Initialize current member info
                    current_member = {
                        'ip_address': ip_address,
                        'port': port,
                        'status': 'enabled',  # Default status
                        'session': None,
                        'state': None
                    }
                    in_member_config = True
                    
                    # Check if this line has immediate closing brace (single line member)
                    if '}' in line:
                        # Single line member, process immediately
                        self._create_node_from_member(current_member, current_pool_name)
                        current_member = None
                        in_member_config = False
                    continue
                
                # Parse member configuration details
                if in_member_config and current_member:
                    # Parse session state
                    session_match = re.match(r'session\s+(.+)', line)
                    if session_match:
                        current_member['session'] = session_match.group(1).strip()
                    
                    # Parse node state
                    state_match = re.match(r'state\s+(.+)', line)
                    if state_match:
                        current_member['state'] = state_match.group(1).strip()
                    
                    # Check for member block end
                    if line == '}':
                        # Determine final status based on session and state
                        if current_member['session'] == 'user-disabled' and current_member['state'] == 'user-down':
                            current_member['status'] = 'disabled'
                        elif current_member['state'] and 'down' in current_member['state'].lower():
                            current_member['status'] = 'offline'
                        elif current_member['session'] and 'disabled' in current_member['session'].lower():
                            current_member['status'] = 'disabled'
                        
                        # Create the node
                        self._create_node_from_member(current_member, current_pool_name)
                        current_member = None
                        in_member_config = False
    
    def _create_node_from_member(self, member_info, pool_name):
        """Create and add a node object from member information"""
        if not member_info or not pool_name:
            return
        
        # Find the pool object by name from database
        from model import LtmPool
        pool_obj = LtmPool.query.filter_by(
            name=pool_name,
            config_file_id=self.config_file_id
        ).first()
        
        if pool_obj:
            node_obj = LtmNode(
                config_file_id=self.config_file_id,
                pool_id=pool_obj.id,
                ip_address=member_info['ip_address'],
                port=member_info['port'],
                node_name=f"{member_info['ip_address']}:{member_info['port']}",
                status=member_info['status']
            )
            self.nodes.append(node_obj)
            db.session.add(node_obj)