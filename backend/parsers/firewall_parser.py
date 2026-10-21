import re
import json
import ipaddress
from model import db, FirewallAddressObject, FirewallAddressGroup, FirewallVipGroup, FirewallPolicy, FirewallNatPolicy

class FirewallConfigParser:
    """
    Multi-format firewall configuration parser supporting:
    
    1. FortiGate format:
       - config firewall address / edit "name" / set subnet IP/mask / next / end
       - config firewall addrgrp / edit "name" / set member "member1" "member2" / next / end  
       - config firewall policy / edit ID / set srcaddr/dstaddr/service/action / next / end
       - NAT policies from firewall policies with "set nat enable" and translation settings
    
    2. Palo Alto format:
       - set address <name> ip-netmask <ip/mask>
       - set address-group <name> static <member> or static [ member1 member2 ... ]
       - set rulebase security rules <name> <attribute> <value>
       - set rulebase nat rules <name> <attribute> <value> for NAT policies
    """
    def __init__(self, config_content, config_file_id):
        self.config_content = config_content
        self.config_file_id = config_file_id
        self.address_objects = []
        self.address_groups = []
        self.vip_groups = []
        self.policies = []
        self.nat_policies = []
        self.config_type = self._detect_config_type()
    
    def _detect_config_type(self):
        """Detect if config is FortiGate or Palo Alto format"""
        if 'config firewall address' in self.config_content:
            return 'fortigate'
        elif 'set address ' in self.config_content:
            return 'paloalto'
        else:
            return 'unknown'
    
    def parse(self):
        """Parse Firewall configuration and extract all components"""
        lines = self.config_content.split('\n')
        
        if self.config_type == 'fortigate':
            # Parse address objects first
            self._parse_fortigate_address_objects(lines)
            # Parse address groups
            self._parse_fortigate_address_groups(lines)
            # Parse VIP groups (FortiGate-specific)
            self._parse_fortigate_vip_groups(lines)
            # Resolve group members after all objects and groups are parsed
            self._resolve_all_group_members()
            # Resolve VIP group members after all VIPs are parsed
            self._resolve_all_vip_group_members()
            # Parse firewall policies
            self._parse_fortigate_policies(lines)
            # Parse NAT policies
            self._parse_fortigate_nat_policies(lines)
        elif self.config_type == 'paloalto':
            # Parse address objects first
            self._parse_paloalto_address_objects(lines)
            # Parse address groups
            self._parse_paloalto_address_groups(lines)
            # Resolve group members after all objects and groups are parsed
            self._resolve_all_group_members()
            # Parse firewall policies
            self._parse_paloalto_policies(lines)
            # Parse NAT policies
            self._parse_paloalto_nat_policies(lines)
        
        return {
            'config_type': self.config_type,
            'address_objects': len(self.address_objects),
            'address_groups': len(self.address_groups),
            'policies': len(self.policies),
            'nat_policies': len(self.nat_policies)
        }
    
    def _resolve_all_group_members(self):
        """Pre-compute resolved member IPs for all address groups"""
        # Create lookup maps for efficiency
        address_map = {}
        group_map = {}

        # Build address object lookup
        for addr_obj in self.address_objects:
            name = addr_obj.name
            display_ip = addr_obj.cidr_notation or addr_obj.ip_address
            if not addr_obj.cidr_notation and addr_obj.ip_address and addr_obj.object_type == 'host':
                display_ip = f"{addr_obj.ip_address}/32"
            address_map[name] = display_ip

        # Build initial group member lookup
        for group in self.address_groups:
            if group.members:
                try:
                    members = json.loads(group.members) if isinstance(group.members, str) else group.members
                    group_map[group.name] = members
                except Exception:
                    group_map[group.name] = []

        # Resolve groups with limited recursion depth to prevent infinite loops
        def resolve_members_with_names(member_names, visited=None, depth=0):
            if depth > 3 or not member_names:  # Limit recursion depth
                return [], []

            if visited is None:
                visited = set()

            resolved_ips = []
            member_details = []

            for member_name in member_names:  # Process all members in group
                if member_name in visited:
                    resolved_ips.append(f"Circular: {member_name}")
                    member_details.append({"name": member_name, "ip": f"Circular: {member_name}", "type": "circular"})
                    continue

                visited.add(member_name)

                # Check if it's an address object
                if member_name in address_map:
                    ip = address_map[member_name]
                    resolved_ips.append(ip)
                    member_details.append({"name": member_name, "ip": ip, "type": "address"})
                # Check if it's a nested group
                elif member_name in group_map:
                    nested_members = group_map[member_name]
                    nested_ips, nested_details = resolve_members_with_names(nested_members, visited.copy(), depth + 1)
                    resolved_ips.extend(nested_ips)  # No limit on nested resolution
                    member_details.append({"name": member_name, "ip": f"Group with {len(nested_ips)} members", "type": "group", "nested_members": nested_details})
                else:
                    resolved_ips.append(f"Missing: {member_name}")
                    member_details.append({"name": member_name, "ip": f"Missing: {member_name}", "type": "missing"})

            return resolved_ips, member_details

        def count_total_ips(member_details):
            """Count all IP addresses in member_details, including nested groups"""
            total_count = 0
            for member in member_details:
                if member.get('type') == 'address':
                    total_count += 1
                elif member.get('type') == 'group' and member.get('nested_members'):
                    total_count += count_total_ips(member['nested_members'])
            return total_count

        # Update each address group with resolved members
        for group in self.address_groups:
            if group.name in group_map:
                member_names = group_map[group.name]
                resolved_ips, member_details = resolve_members_with_names(member_names)

                # Store resolved members and count (backward compatibility)
                group.resolved_members = json.dumps(resolved_ips)  # Store all IPs

                # Calculate correct member count from member_details (includes nested groups)
                total_ip_count = count_total_ips(member_details)
                group.member_count = total_ip_count

                # Store detailed member information with names and IPs
                group.member_details = json.dumps(member_details)  # Store all detailed info

    def _resolve_all_vip_group_members(self):
        """Pre-compute resolved member IPs for all VIP groups by parsing VIP definitions"""
        # Parse VIP definitions from config to build lookup map
        vip_map = {}
        lines = self.config_content.split('\n')

        in_vip_section = False
        current_vip = None
        current_vip_name = None

        for line in lines:
            line = line.strip()

            # Look for firewall vip section (not vipgrp)
            if line == 'config firewall vip':
                in_vip_section = True
                continue

            # Exit firewall vip section
            if in_vip_section and line == 'end':
                # Save the last VIP if exists
                if current_vip_name and current_vip:
                    vip_map[current_vip_name] = current_vip
                in_vip_section = False
                current_vip = None
                current_vip_name = None
                continue

            if in_vip_section:
                # Start of VIP block
                edit_match = re.match(r'edit\s+"(.+?)"', line)
                if edit_match:
                    # Save previous VIP if exists
                    if current_vip_name and current_vip:
                        vip_map[current_vip_name] = current_vip

                    current_vip_name = edit_match.group(1).strip()
                    current_vip = {'extip': None, 'mappedip': None}
                    continue

                # End of VIP block
                if line == 'next':
                    if current_vip_name and current_vip:
                        vip_map[current_vip_name] = current_vip
                    current_vip = None
                    current_vip_name = None
                    continue

                # Parse extip (external IP)
                if current_vip:
                    extip_match = re.match(r'set extip\s+([\d.]+)', line)
                    if extip_match:
                        current_vip['extip'] = extip_match.group(1).strip()

                    # Parse mappedip (internal mapped IP)
                    mappedip_match = re.match(r'set mappedip\s+"?([^"]+)"?', line)
                    if mappedip_match:
                        current_vip['mappedip'] = mappedip_match.group(1).strip().strip('"')

        # Now resolve VIP group members
        for vip_group in self.vip_groups:
            if vip_group.members:
                try:
                    member_names = json.loads(vip_group.members) if isinstance(vip_group.members, str) else vip_group.members
                    resolved_ips = []
                    member_details = []

                    for member_name in member_names:
                        if member_name in vip_map:
                            vip_info = vip_map[member_name]
                            # Use extip as the primary IP for VIP group display
                            ext_ip = vip_info.get('extip')
                            mapped_ip = vip_info.get('mappedip')

                            if ext_ip:
                                resolved_ips.append(f"{ext_ip}/32")
                                member_details.append({
                                    "name": member_name,
                                    "ip": f"{ext_ip}/32",
                                    "mapped_ip": mapped_ip,
                                    "type": "vip"
                                })
                            else:
                                resolved_ips.append(f"Missing IP: {member_name}")
                                member_details.append({
                                    "name": member_name,
                                    "ip": f"Missing IP: {member_name}",
                                    "type": "missing"
                                })
                        else:
                            resolved_ips.append(f"Missing VIP: {member_name}")
                            member_details.append({
                                "name": member_name,
                                "ip": f"Missing VIP: {member_name}",
                                "type": "missing"
                            })

                    # Store resolved members
                    vip_group.resolved_members = json.dumps(resolved_ips)
                    vip_group.member_count = len([ip for ip in resolved_ips if not ip.startswith('Missing')])
                    vip_group.member_details = json.dumps(member_details)

                except Exception as e:
                    vip_group.resolved_members = json.dumps([])
                    vip_group.member_count = 0
                    vip_group.member_details = json.dumps([])

    def _parse_fortigate_address_objects(self, lines):
        """Extract firewall address object configurations"""
        in_firewall_section = False
        current_address = None
        in_address_block = False
        
        for line in lines:
            line = line.strip()
            
            # Look for firewall address section
            if 'config firewall address' in line:
                in_firewall_section = True
                continue
            
            # Exit firewall address section
            if in_firewall_section and line == 'end':
                in_firewall_section = False
                continue
            
            if in_firewall_section:
                # Start of address object block
                edit_match = re.match(r'edit\s+"(.+?)"', line)
                if edit_match:
                    addr_name = edit_match.group(1).strip()
                    current_address = {
                        'name': addr_name,
                        'ip_address': None,
                        'subnet_mask': None,
                        'cidr_notation': None,
                        'object_type': 'host'
                    }
                    in_address_block = True
                    continue
                
                # End of address block
                if in_address_block and line == 'next':
                    if current_address and current_address['name']:
                        addr_obj = FirewallAddressObject(
                            config_file_id=self.config_file_id,
                            name=current_address['name'],
                            ip_address=current_address['ip_address'],
                            subnet_mask=current_address['subnet_mask'],
                            cidr_notation=current_address['cidr_notation'],
                            object_type=current_address['object_type']
                        )
                        self.address_objects.append(addr_obj)
                        db.session.add(addr_obj)
                    
                    current_address = None
                    in_address_block = False
                    continue
                
                # Parse address properties
                if in_address_block and current_address:
                    # Subnet format: set subnet IP/mask or IP netmask
                    subnet_match = re.match(r'set subnet\s+(\S+)\s+(\S+)', line)
                    if subnet_match:
                        ip_or_subnet = subnet_match.group(1)
                        mask = subnet_match.group(2)
                        
                        # Check if it's CIDR notation
                        if '/' in ip_or_subnet:
                            current_address['cidr_notation'] = ip_or_subnet
                            current_address['ip_address'] = ip_or_subnet.split('/')[0]
                            current_address['object_type'] = 'subnet'
                        else:
                            current_address['ip_address'] = ip_or_subnet
                            current_address['subnet_mask'] = mask
                            # Convert to CIDR if possible
                            try:
                                network = ipaddress.IPv4Network(f"{ip_or_subnet}/{mask}", strict=False)
                                current_address['cidr_notation'] = str(network)
                                if network.num_addresses > 1:
                                    current_address['object_type'] = 'subnet'
                            except Exception:
                                pass
                    
                    # Alternative subnet format
                    alt_subnet_match = re.match(r'set subnet\s+(\S+/\d+)', line)
                    if alt_subnet_match:
                        cidr = alt_subnet_match.group(1)
                        current_address['cidr_notation'] = cidr
                        current_address['ip_address'] = cidr.split('/')[0]
                        current_address['object_type'] = 'subnet'
    
    def _parse_fortigate_address_groups(self, lines):
        """Extract firewall address group configurations"""
        in_addrgrp_section = False
        current_group = None
        in_group_block = False
        
        for line in lines:
            line = line.strip()
            
            # Look for firewall addrgrp section
            if 'config firewall addrgrp' in line:
                in_addrgrp_section = True
                continue
            
            # Exit firewall addrgrp section
            if in_addrgrp_section and line == 'end':
                in_addrgrp_section = False
                continue
            
            if in_addrgrp_section:
                # Start of group block
                edit_match = re.match(r'edit\s+"(.+?)"', line)
                if edit_match:
                    group_name = edit_match.group(1).strip()
                    current_group = {
                        'name': group_name,
                        'members': []
                    }
                    in_group_block = True
                    continue
                
                # End of group block
                if in_group_block and line == 'next':
                    if current_group and current_group['name']:
                        group_obj = FirewallAddressGroup(
                            config_file_id=self.config_file_id,
                            name=current_group['name'],
                            members=json.dumps(current_group['members'])
                        )
                        self.address_groups.append(group_obj)
                        db.session.add(group_obj)
                    
                    current_group = None
                    in_group_block = False
                    continue
                
                # Parse group members
                if in_group_block and current_group:
                    member_match = re.match(r'set member\s+"(.+)"', line)
                    if member_match:
                        members = [m.strip().strip('"') for m in member_match.group(1).split('" "')]
                        current_group['members'].extend(members)

    def _parse_fortigate_vip_groups(self, lines):
        """Extract firewall VIP group configurations"""
        in_vipgrp_section = False
        current_group = None
        in_group_block = False

        for line in lines:
            line = line.strip()

            # Look for firewall vipgrp section
            if 'config firewall vipgrp' in line:
                in_vipgrp_section = True
                continue

            # Exit firewall vipgrp section
            if in_vipgrp_section and line == 'end':
                in_vipgrp_section = False
                continue

            if in_vipgrp_section:
                # Start of VIP group block
                edit_match = re.match(r'edit\s+"(.+?)"', line)
                if edit_match:
                    group_name = edit_match.group(1).strip()
                    current_group = {
                        'name': group_name,
                        'members': []
                    }
                    in_group_block = True
                    continue

                # End of VIP group block
                if in_group_block and line == 'next':
                    if current_group and current_group['name']:
                        group_obj = FirewallVipGroup(
                            config_file_id=self.config_file_id,
                            name=current_group['name'],
                            members=json.dumps(current_group['members'])
                        )
                        self.vip_groups.append(group_obj)
                        db.session.add(group_obj)

                    current_group = None
                    in_group_block = False
                    continue

                # Parse VIP group members
                if in_group_block and current_group:
                    member_match = re.match(r'set member\s+"(.+)"', line)
                    if member_match:
                        members = [m.strip().strip('"') for m in member_match.group(1).split('" "')]
                        current_group['members'].extend(members)

    def _parse_fortigate_policies(self, lines):
        """Extract firewall policy configurations"""
        in_policy_section = False
        current_policy = None
        in_policy_block = False
        
        for line in lines:
            line = line.strip()
            
            # Look for firewall policy section
            if 'config firewall policy' in line:
                in_policy_section = True
                continue
            
            # Exit firewall policy section
            if in_policy_section and line == 'end':
                in_policy_section = False
                continue
            
            if in_policy_section:
                # Start of policy block
                edit_match = re.match(r'edit\s+(\d+)', line)
                if edit_match:
                    policy_id = edit_match.group(1).strip()
                    current_policy = {
                        'policy_id': policy_id,
                        'name': None,
                        'source_addresses': [],
                        'destination_addresses': [],
                        'source_zone': None,
                        'destination_zone': None,
                        'services': [],
                        'action': 'Allow',
                        'status': 'enable'
                    }
                    in_policy_block = True
                    continue
                
                # End of policy block
                if in_policy_block and line == 'next':
                    if current_policy and current_policy['policy_id']:
                        policy_obj = FirewallPolicy(
                            config_file_id=self.config_file_id,
                            policy_id=current_policy['policy_id'],
                            name=current_policy['name'],
                            source_addresses=json.dumps(current_policy['source_addresses']),
                            destination_addresses=json.dumps(current_policy['destination_addresses']),
                            source_zone=current_policy['source_zone'],
                            destination_zone=current_policy['destination_zone'],
                            services=json.dumps(current_policy['services']),
                            action=current_policy['action'],
                            status=current_policy['status']
                        )
                        self.policies.append(policy_obj)
                        db.session.add(policy_obj)
                    
                    current_policy = None
                    in_policy_block = False
                    continue
                
                # Parse policy properties
                if in_policy_block and current_policy:
                    # Name
                    name_match = re.match(r'set name\s+"(.+?)"', line)
                    if name_match:
                        current_policy['name'] = name_match.group(1)
                    
                    # Source addresses
                    srcaddr_match = re.match(r'set srcaddr\s+"(.+)"', line)
                    if srcaddr_match:
                        sources = [s.strip().strip('"') for s in srcaddr_match.group(1).split('" "')]
                        current_policy['source_addresses'] = sources
                    
                    # Destination addresses
                    dstaddr_match = re.match(r'set dstaddr\s+"(.+)"', line)
                    if dstaddr_match:
                        destinations = [d.strip().strip('"') for d in dstaddr_match.group(1).split('" "')]
                        current_policy['destination_addresses'] = destinations
                    
                    # Services
                    service_match = re.match(r'set service\s+"(.+)"', line)
                    if service_match:
                        services = [s.strip().strip('"') for s in service_match.group(1).split('" "')]
                        current_policy['services'] = services
                    
                    # Action
                    action_match = re.match(r'set action\s+(\w+)', line)
                    if action_match:
                        current_policy['action'] = action_match.group(1)
                    
                    # Status
                    if 'set status disable' in line:
                        current_policy['status'] = 'disable'
                    elif 'set status enable' in line:
                        current_policy['status'] = 'enable'
                    
                    # Source interface/zone
                    srcintf_match = re.match(r'set srcintf\s+"(.+?)"', line)
                    if srcintf_match:
                        current_policy['source_zone'] = srcintf_match.group(1)
                    
                    # Destination interface/zone
                    dstintf_match = re.match(r'set dstintf\s+"(.+?)"', line)
                    if dstintf_match:
                        current_policy['destination_zone'] = dstintf_match.group(1)
    
    def _parse_fortigate_nat_policies(self, lines):
        """Extract FortiGate NAT policy configurations from firewall policies with NAT enabled"""
        in_policy_section = False
        current_policy = None
        in_policy_block = False
        
        for line in lines:
            line = line.strip()
            
            # Look for firewall policy section
            if 'config firewall policy' in line:
                in_policy_section = True
                continue
            
            # Exit firewall policy section
            if in_policy_section and line == 'end':
                in_policy_section = False
                continue
            
            if in_policy_section:
                # Start of policy block
                edit_match = re.match(r'edit\s+(\d+)', line)
                if edit_match:
                    policy_id = edit_match.group(1).strip()
                    current_policy = {
                        'policy_id': policy_id,
                        'name': None,
                        'source_addresses': [],
                        'destination_addresses': [],
                        'source_zone': None,
                        'destination_zone': None,
                        'services': [],
                        'status': 'enable',
                        'nat_enabled': False,
                        'source_translation': {},
                        'destination_translation': {},
                        'srcaddr_negate': False,
                        'dstaddr_negate': False,
                        'outbound_interface': None
                    }
                    in_policy_block = True
                    continue
                
                # End of policy block
                if in_policy_block and line == 'next':
                    # Only create NAT policy if NAT is enabled
                    if current_policy and current_policy['policy_id'] and current_policy['nat_enabled']:
                        nat_policy_obj = FirewallNatPolicy(
                            config_file_id=self.config_file_id,
                            policy_id=current_policy['policy_id'],
                            name=current_policy['name'],
                            source_addresses=json.dumps(current_policy['source_addresses']),
                            destination_addresses=json.dumps(current_policy['destination_addresses']),
                            source_zone=current_policy['source_zone'],
                            destination_zone=current_policy['destination_zone'],
                            services=json.dumps(current_policy['services']),
                            source_translation=json.dumps(current_policy['source_translation']),
                            destination_translation=json.dumps(current_policy['destination_translation']),
                            status=current_policy['status']
                        )
                        self.nat_policies.append(nat_policy_obj)
                        db.session.add(nat_policy_obj)
                    
                    current_policy = None
                    in_policy_block = False
                    continue
                
                # Parse policy properties
                if in_policy_block and current_policy:
                    # Name
                    name_match = re.match(r'set name\s+"(.+?)"', line)
                    if name_match:
                        current_policy['name'] = name_match.group(1)
                    
                    # Source addresses
                    srcaddr_match = re.match(r'set srcaddr\s+"(.+)"', line)
                    if srcaddr_match:
                        sources = [s.strip().strip('"') for s in srcaddr_match.group(1).split('" "')]
                        current_policy['source_addresses'] = sources
                    
                    # Destination addresses
                    dstaddr_match = re.match(r'set dstaddr\s+"(.+)"', line)
                    if dstaddr_match:
                        destinations = [d.strip().strip('"') for d in dstaddr_match.group(1).split('" "')]
                        current_policy['destination_addresses'] = destinations
                    
                    # Services
                    service_match = re.match(r'set service\s+"(.+)"', line)
                    if service_match:
                        services = [s.strip().strip('"') for s in service_match.group(1).split('" "')]
                        current_policy['services'] = services
                    
                    # Status
                    if 'set status disable' in line:
                        current_policy['status'] = 'disable'
                    elif 'set status enable' in line:
                        current_policy['status'] = 'enable'
                    
                    # Source interface/zone
                    srcintf_match = re.match(r'set srcintf\s+"(.+?)"', line)
                    if srcintf_match:
                        current_policy['source_zone'] = srcintf_match.group(1)
                    
                    # Destination interface/zone
                    dstintf_match = re.match(r'set dstintf\s+"(.+?)"', line)
                    if dstintf_match:
                        current_policy['destination_zone'] = dstintf_match.group(1)
                    
                    # NAT enable
                    if 'set nat enable' in line:
                        current_policy['nat_enabled'] = True
                    
                    # Source address negation
                    if 'set srcaddr-negate enable' in line:
                        current_policy['srcaddr_negate'] = True
                        current_policy['source_translation']['negate'] = True
                    
                    # Destination address negation
                    if 'set dstaddr-negate enable' in line:
                        current_policy['dstaddr_negate'] = True
                        current_policy['destination_translation']['negate'] = True
                    
                    # NAT pool/IP
                    natip_match = re.match(r'set natip\s+"(.+?)"', line)
                    if natip_match:
                        current_policy['source_translation']['translated_ip'] = natip_match.group(1)
                        current_policy['source_translation']['type'] = 'static-ip'
                    
                    # Dynamic IP pool
                    ippool_match = re.match(r'set ippool\s+"(.+?)"', line)
                    if ippool_match:
                        current_policy['source_translation']['ip_pool'] = ippool_match.group(1)
                        current_policy['source_translation']['type'] = 'dynamic-ip-pool'
                    
                    # Outbound interface for destination NAT
                    outbound_match = re.match(r'set outbound-interface\s+"(.+?)"', line)
                    if outbound_match:
                        current_policy['outbound_interface'] = outbound_match.group(1)
                        current_policy['destination_translation']['outbound_interface'] = outbound_match.group(1)
                    
                    # NAT source port
                    natsourceport_match = re.match(r'set nat-sourceport\s+(\d+)-(\d+)', line)
                    if natsourceport_match:
                        current_policy['source_translation']['port_range'] = f"{natsourceport_match.group(1)}-{natsourceport_match.group(2)}"
                    
                    # Fixed port
                    if 'set fixedport enable' in line:
                        current_policy['source_translation']['fixed_port'] = True
                    elif 'set fixedport disable' in line:
                        current_policy['source_translation']['fixed_port'] = False
    
    def _parse_paloalto_address_objects(self, lines):
        """Extract Palo Alto address object configurations"""
        for line in lines:
            line = line.strip()
            
            # Parse address objects: set address <name> ip-netmask <ip/mask>
            addr_match = re.match(r'set address\s+(\S+)\s+ip-netmask\s+(\S+)', line)
            if addr_match:
                addr_name = addr_match.group(1)
                ip_cidr = addr_match.group(2)
                
                # Extract IP and determine type
                if '/' in ip_cidr:
                    ip_address = ip_cidr.split('/')[0]
                    cidr_notation = ip_cidr
                    try:
                        network = ipaddress.IPv4Network(ip_cidr, strict=False)
                        object_type = 'subnet' if network.num_addresses > 1 else 'host'
                    except Exception:
                        object_type = 'host'
                else:
                    ip_address = ip_cidr
                    cidr_notation = f"{ip_cidr}/32"
                    object_type = 'host'
                
                addr_obj = FirewallAddressObject(
                    config_file_id=self.config_file_id,
                    name=addr_name,
                    ip_address=ip_address,
                    subnet_mask=None,
                    cidr_notation=cidr_notation,
                    object_type=object_type
                )
                self.address_objects.append(addr_obj)
                db.session.add(addr_obj)
    
    def _parse_paloalto_address_groups(self, lines):
        """Extract Palo Alto address group configurations"""
        for line in lines:
            line = line.strip()
            
            # Parse address groups: set address-group <name> static <member> or static [ member1 member2 ... ]
            # Single member format
            group_single_match = re.match(r'set address-group\s+(\S+)\s+static\s+(\S+)$', line)
            if group_single_match:
                group_name = group_single_match.group(1)
                member = group_single_match.group(2)
                
                # Check if this group already exists
                existing_group = None
                for group in self.address_groups:
                    if group.name == group_name:
                        existing_group = group
                        break
                
                if existing_group:
                    # Add member to existing group
                    members = json.loads(existing_group.members)
                    if member not in members:
                        members.append(member)
                        existing_group.members = json.dumps(members)
                else:
                    # Create new group
                    group_obj = FirewallAddressGroup(
                        config_file_id=self.config_file_id,
                        name=group_name,
                        members=json.dumps([member])
                    )
                    self.address_groups.append(group_obj)
                    db.session.add(group_obj)
            
            # Multiple members format: static [ member1 member2 ... ]
            group_multi_match = re.match(r'set address-group\s+(\S+)\s+static\s+\[\s*(.+?)\s*\]', line)
            if group_multi_match:
                group_name = group_multi_match.group(1)
                members_str = group_multi_match.group(2)
                members = [m.strip() for m in members_str.split() if m.strip()]
                
                group_obj = FirewallAddressGroup(
                    config_file_id=self.config_file_id,
                    name=group_name,
                    members=json.dumps(members)
                )
                self.address_groups.append(group_obj)
                db.session.add(group_obj)
    
    def _parse_paloalto_policies(self, lines):
        """Extract Palo Alto security policy configurations"""
        policies_dict = {}
        
        for line in lines:
            line = line.strip()
            
            # Parse security rules: set rulebase security rules <rule_name> <attribute> <value>
            policy_match = re.match(r'set rulebase security rules\s+(\S+)\s+(.+)', line)
            if policy_match:
                rule_name = policy_match.group(1)
                rest = policy_match.group(2).strip()
                
                # Initialize policy if not exists
                if rule_name not in policies_dict:
                    policies_dict[rule_name] = {
                        'policy_id': rule_name,
                        'name': rule_name,
                        'source_addresses': [],
                        'destination_addresses': [],
                        'source_zone': None,
                        'destination_zone': None,
                        'services': [],
                        'action': 'Allow',
                        'status': 'enable'
                    }
                
                current_policy = policies_dict[rule_name]
                
                # Parse different attributes
                if rest.startswith('from '):
                    current_policy['source_zone'] = rest[5:].strip()
                elif rest.startswith('to '):
                    current_policy['destination_zone'] = rest[3:].strip()
                elif rest.startswith('source '):
                    source = rest[7:].strip()
                    if source != 'any':
                        # Handle bracket notation for multiple sources
                        if source.startswith('[') and source.endswith(']'):
                            sources = [s.strip() for s in source[1:-1].split() if s.strip()]
                            for s in sources:
                                if s not in current_policy['source_addresses']:
                                    current_policy['source_addresses'].append(s)
                        elif source not in current_policy['source_addresses']:
                            current_policy['source_addresses'].append(source)
                elif rest.startswith('destination '):
                    dest = rest[12:].strip()
                    if dest != 'any':
                        # Handle bracket notation for multiple destinations
                        if dest.startswith('[') and dest.endswith(']'):
                            destinations = [d.strip() for d in dest[1:-1].split() if d.strip()]
                            for d in destinations:
                                if d not in current_policy['destination_addresses']:
                                    current_policy['destination_addresses'].append(d)
                        elif dest not in current_policy['destination_addresses']:
                            current_policy['destination_addresses'].append(dest)
                elif rest.startswith('service '):
                    service = rest[8:].strip()
                    if service != 'any':
                        # Handle bracket notation for multiple services
                        if service.startswith('[') and service.endswith(']'):
                            services = [s.strip() for s in service[1:-1].split() if s.strip()]
                            for s in services:
                                if s not in current_policy['services']:
                                    current_policy['services'].append(s)
                        elif service not in current_policy['services']:
                            current_policy['services'].append(service)
                elif rest.startswith('application '):
                    app = rest[12:].strip()
                    if app != 'any' and app not in current_policy['services']:
                        current_policy['services'].append(app)
                elif rest.startswith('action '):
                    current_policy['action'] = rest[7:].strip()
                elif rest == 'disabled yes':
                    current_policy['status'] = 'disable'
        
        # Convert policies dict to objects
        for policy_data in policies_dict.values():
            policy_obj = FirewallPolicy(
                config_file_id=self.config_file_id,
                policy_id=policy_data['policy_id'],
                name=policy_data['name'],
                source_addresses=json.dumps(policy_data['source_addresses']),
                destination_addresses=json.dumps(policy_data['destination_addresses']),
                source_zone=policy_data['source_zone'],
                destination_zone=policy_data['destination_zone'],
                services=json.dumps(policy_data['services']),
                action=policy_data['action'],
                status=policy_data['status']
            )
            self.policies.append(policy_obj)
            db.session.add(policy_obj)
    
    def _parse_paloalto_nat_policies(self, lines):
        """Extract Palo Alto NAT policy configurations"""
        nat_policies_dict = {}
        
        for line in lines:
            line = line.strip()
            
            # Parse NAT rules: set rulebase nat rules <rule_name> <attribute> <value>
            nat_match = re.match(r'set rulebase nat rules\s+(\S+)\s+(.+)', line)
            if nat_match:
                rule_name = nat_match.group(1)
                rest = nat_match.group(2).strip()
                
                # Initialize NAT policy if not exists
                if rule_name not in nat_policies_dict:
                    nat_policies_dict[rule_name] = {
                        'policy_id': rule_name,
                        'name': rule_name,
                        'source_addresses': [],
                        'destination_addresses': [],
                        'source_zone': None,
                        'destination_zone': None,
                        'services': [],
                        'status': 'enable',
                        'source_translation': {},
                        'destination_translation': {}
                    }
                
                current_nat_policy = nat_policies_dict[rule_name]
                
                # Parse different NAT attributes
                if rest.startswith('from '):
                    current_nat_policy['source_zone'] = rest[5:].strip()
                elif rest.startswith('to '):
                    current_nat_policy['destination_zone'] = rest[3:].strip()
                elif rest.startswith('source '):
                    source = rest[7:].strip()
                    if source != 'any':
                        # Handle bracket notation for multiple sources
                        if source.startswith('[') and source.endswith(']'):
                            sources = [s.strip() for s in source[1:-1].split() if s.strip()]
                            for s in sources:
                                if s not in current_nat_policy['source_addresses']:
                                    current_nat_policy['source_addresses'].append(s)
                        elif source not in current_nat_policy['source_addresses']:
                            current_nat_policy['source_addresses'].append(source)
                elif rest.startswith('destination '):
                    dest = rest[12:].strip()
                    if dest != 'any':
                        # Handle bracket notation for multiple destinations
                        if dest.startswith('[') and dest.endswith(']'):
                            destinations = [d.strip() for d in dest[1:-1].split() if d.strip()]
                            for d in destinations:
                                if d not in current_nat_policy['destination_addresses']:
                                    current_nat_policy['destination_addresses'].append(d)
                        elif dest not in current_nat_policy['destination_addresses']:
                            current_nat_policy['destination_addresses'].append(dest)
                elif rest.startswith('service '):
                    service = rest[8:].strip()
                    if service != 'any':
                        # Handle bracket notation for multiple services
                        if service.startswith('[') and service.endswith(']'):
                            services = [s.strip() for s in service[1:-1].split() if s.strip()]
                            for s in services:
                                if s not in current_nat_policy['services']:
                                    current_nat_policy['services'].append(s)
                        elif service not in current_nat_policy['services']:
                            current_nat_policy['services'].append(service)
                elif rest == 'disabled yes':
                    current_nat_policy['status'] = 'disable'
                
                # Source translation types
                elif rest.startswith('source-translation dynamic-ip-and-port'):
                    current_nat_policy['source_translation']['type'] = 'dynamic-ip-and-port'
                    # Extract interface or pool details
                    if 'interface-address' in rest:
                        interface_match = re.search(r'interface-address\s+interface\s+(\S+)', rest)
                        if interface_match:
                            current_nat_policy['source_translation']['interface'] = interface_match.group(1)
                    elif 'translated-address' in rest:
                        address_match = re.search(r'translated-address\s+(\S+)', rest)
                        if address_match:
                            current_nat_policy['source_translation']['translated_address'] = address_match.group(1)
                
                elif rest.startswith('source-translation static-ip'):
                    current_nat_policy['source_translation']['type'] = 'static-ip'
                    # Extract static IP mapping
                    static_match = re.search(r'translated-address\s+(\S+)', rest)
                    if static_match:
                        current_nat_policy['source_translation']['translated_address'] = static_match.group(1)
                    # Bi-directional flag
                    if 'bi-directional' in rest:
                        current_nat_policy['source_translation']['bi_directional'] = 'yes' in rest
                
                elif rest.startswith('source-translation dynamic-ip'):
                    current_nat_policy['source_translation']['type'] = 'dynamic-ip'
                    # Extract translated address pool
                    pool_match = re.search(r'translated-address\s+(\S+)', rest)
                    if pool_match:
                        current_nat_policy['source_translation']['translated_address'] = pool_match.group(1)
                
                # Destination translation types
                elif rest.startswith('destination-translation static-ip'):
                    current_nat_policy['destination_translation']['type'] = 'static-ip'
                    # Extract static IP mapping
                    dest_ip_match = re.search(r'translated-address\s+(\S+)', rest)
                    if dest_ip_match:
                        current_nat_policy['destination_translation']['translated_address'] = dest_ip_match.group(1)
                    # Extract port mapping
                    dest_port_match = re.search(r'translated-port\s+(\d+)', rest)
                    if dest_port_match:
                        current_nat_policy['destination_translation']['translated_port'] = dest_port_match.group(1)
                
                elif rest.startswith('destination-translation dynamic-ip'):
                    current_nat_policy['destination_translation']['type'] = 'dynamic-ip'
                    # Extract translated address pool
                    dest_pool_match = re.search(r'translated-address\s+(\S+)', rest)
                    if dest_pool_match:
                        current_nat_policy['destination_translation']['translated_address'] = dest_pool_match.group(1)
                    # Extract port mapping
                    dest_dyn_port_match = re.search(r'translated-port\s+(\d+)', rest)
                    if dest_dyn_port_match:
                        current_nat_policy['destination_translation']['translated_port'] = dest_dyn_port_match.group(1)
                
                # Handle simple destination-translation format: destination-translation translated-address <address>
                elif rest.startswith('destination-translation translated-address'):
                    current_nat_policy['destination_translation']['type'] = 'static-ip'
                    # Extract translated address
                    simple_dest_match = re.search(r'translated-address\s+(\S+)', rest)
                    if simple_dest_match:
                        current_nat_policy['destination_translation']['translated_address'] = simple_dest_match.group(1)

                # Handle alternate format: dynamic-destination-translation translated-address <address>
                elif rest.startswith('dynamic-destination-translation'):
                    current_nat_policy['destination_translation']['type'] = 'dynamic-ip'
                    # Extract translated address
                    dyn_dest_match = re.search(r'translated-address\s+(\S+)', rest)
                    if dyn_dest_match:
                        current_nat_policy['destination_translation']['translated_address'] = dyn_dest_match.group(1)
                    # Extract port mapping if present
                    dyn_dest_port_match = re.search(r'translated-port\s+(\d+)', rest)
                    if dyn_dest_port_match:
                        current_nat_policy['destination_translation']['translated_port'] = dyn_dest_port_match.group(1)
                
                # Handle tag/description
                elif rest.startswith('tag '):
                    current_nat_policy['tag'] = rest[4:].strip()
        
        # Convert NAT policies dict to objects
        for nat_policy_data in nat_policies_dict.values():
            # Only create NAT policy if it has translation configuration
            has_translation = (bool(nat_policy_data['source_translation']) or 
                             bool(nat_policy_data['destination_translation']))
            
            if has_translation:
                nat_policy_obj = FirewallNatPolicy(
                    config_file_id=self.config_file_id,
                    policy_id=nat_policy_data['policy_id'],
                    name=nat_policy_data['name'],
                    source_addresses=json.dumps(nat_policy_data['source_addresses']),
                    destination_addresses=json.dumps(nat_policy_data['destination_addresses']),
                    source_zone=nat_policy_data['source_zone'],
                    destination_zone=nat_policy_data['destination_zone'],
                    services=json.dumps(nat_policy_data['services']),
                    source_translation=json.dumps(nat_policy_data['source_translation']),
                    destination_translation=json.dumps(nat_policy_data['destination_translation']),
                    status=nat_policy_data['status'],
                    tag=nat_policy_data.get('tag')
                )
                self.nat_policies.append(nat_policy_obj)
                db.session.add(nat_policy_obj)