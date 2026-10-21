
from sqlalchemy.dialects.postgresql import JSON
# import datetime
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.sqltypes import TIMESTAMP
db = SQLAlchemy()

def utc_plus_8():
    return datetime.utcnow() + timedelta(hours=8)


# Network Configuration Portal Models
class ConfigFile(db.Model):
    __tablename__ = "config_files"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # 'ltm', 'fw_prod', 'fw_admin', 'firewall'
    upload_date = db.Column(db.DateTime, default=utc_plus_8)
    file_path = db.Column(db.String(500))
    source_url = db.Column(db.String(500))  # URL where the config was downloaded from
    parsed_status = db.Column(db.String(50), default='pending')  # 'pending', 'parsed', 'error'
    
    @property
    def serialize(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "upload_date": self.upload_date.strftime("%Y-%m-%d %H:%M:%S") if self.upload_date else None,
            "parsed_status": self.parsed_status
        }


class LtmVirtualServer(db.Model):
    __tablename__ = "ltm_virtual_servers"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    name = db.Column(db.String(255), nullable=False)
    destination_ip = db.Column(db.String(45))  # IP address
    destination_port = db.Column(db.Integer)
    pool_name = db.Column(db.String(255))
    enabled = db.Column(db.Boolean)
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='ltm_virtual_servers')
    
    @property
    def serialize(self):
        env_name = "Unknown"
        if self.config_file:
            if self.config_file.file_type == 'ltm':
                # Determine environment from filename
                filename = self.config_file.filename
                if 'CHARLIE-LTM01' in filename:
                    env_name = "Charlie LTM"
                elif 'DELTA-LTM01' in filename:
                    env_name = "Delta LTM"
                elif 'BRAVO-LTM01' in filename:
                    env_name = "Bravo LTM"
                elif 'ALPHA-UAT-SLB01' in filename:
                    env_name = "Alpha UAT SLB"
                elif 'ADMIN-LTM01' in filename:
                    env_name = "Admin LTM"
                elif 'H2SLB01.TRZ.PRD' in filename:
                    env_name = "H2SLB TRZ PRD"
                elif 'ALPHA-LTM01' in filename:
                    env_name = "Alpha LTM"
                else:
                    env_name = "LTM"
        
        return {
            "id": self.id,
            "name": self.name,
            "destination_ip": self.destination_ip,
            "destination_port": self.destination_port,
            "pool_name": self.pool_name,
            "enabled": self.enabled,
            "environment": env_name
        }


class LtmPool(db.Model):
    __tablename__ = "ltm_pools"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    name = db.Column(db.String(255), nullable=False)
    monitor = db.Column(db.String(255))
    load_balancing_method = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='ltm_pools')
    
    @property
    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "monitor": self.monitor,
            "load_balancing_method": self.load_balancing_method
        }


class LtmNode(db.Model):
    __tablename__ = "ltm_nodes"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    pool_id = db.Column(db.Integer, db.ForeignKey('ltm_pools.id'))
    ip_address = db.Column(db.String(45), nullable=False)
    port = db.Column(db.String(50))
    status = db.Column(db.String(50))
    node_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='ltm_nodes')
    pool = db.relationship('LtmPool', backref='nodes')
    
    @property
    def serialize(self):
        return {
            "id": self.id,
            "name": self.node_name or self.ip_address,
            "ip_address": self.ip_address,
            "port": self.port,
            "status": self.status,
            "node_name": self.node_name,
            "pool_name": self.pool.name if self.pool else None
        }


class FirewallAddressObject(db.Model):
    __tablename__ = "firewall_address_objects"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    name = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45))
    subnet_mask = db.Column(db.String(45))
    cidr_notation = db.Column(db.String(50))
    object_type = db.Column(db.String(50))  # 'subnet', 'host', 'range'
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='firewall_address_objects')
    
    @property
    def serialize(self):
        env_name = "Unknown"
        config_type = "unknown"
        if self.config_file:
            # Detect config type based on filename (Palo Alto files have ADMIN-FW01 pattern)
            filename = self.config_file.filename
            if 'ADMIN-FW01' in filename:
                config_type = "paloalto"
            else:
                config_type = "fortigate"

            if self.config_file.file_type == 'fw_prod':
                env_name = "Delta PROD FW"
            elif self.config_file.file_type == 'fw_admin':
                env_name = "Delta ADMIN FW"
            elif self.config_file.file_type == 'firewall':
                # Determine environment from filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'ADMIN-FW01' in filename:
                    env_name = "Admin FW"
                else:
                    env_name = "Firewall"

        return {
            "id": self.id,
            "name": self.name,
            "ip_address": self.ip_address,
            "subnet_mask": self.subnet_mask,
            "cidr_notation": self.cidr_notation,
            "object_type": self.object_type,
            "environment": env_name,
            "config_type": config_type
        }


class FirewallAddressGroup(db.Model):
    __tablename__ = "firewall_address_groups"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    name = db.Column(db.String(255), nullable=False)
    members = db.Column(db.Text)  # JSON array of member object names
    resolved_members = db.Column(db.Text)  # Pre-computed resolved member IPs (JSON)
    member_count = db.Column(db.Integer, default=0)  # Number of resolved members
    member_details = db.Column(db.Text(4294967295))  # LONGTEXT for detailed member info with names and IPs (JSON)
    created_at = db.Column(db.DateTime, default=utc_plus_8)

    # Relationships
    config_file = db.relationship('ConfigFile', backref='firewall_address_groups')

    @property
    def serialize(self):
        env_name = "Unknown"
        config_type = "unknown"
        if self.config_file:
            # Detect config type based on filename (Palo Alto files have ADMIN-FW01 pattern)
            filename = self.config_file.filename
            if 'ADMIN-FW01' in filename:
                config_type = "paloalto"
            else:
                config_type = "fortigate"

            if self.config_file.file_type == 'fw_prod':
                env_name = "Delta PROD FW"
            elif self.config_file.file_type == 'fw_admin':
                env_name = "Delta ADMIN FW"
            elif self.config_file.file_type == 'firewall':
                # Determine environment from filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'ADMIN-FW01' in filename:
                    env_name = "Admin FW"
                else:
                    env_name = "Firewall"

        return {
            "id": self.id,
            "name": self.name,
            "members": self.members,
            "resolved_members": self.resolved_members,
            "member_count": self.member_count,
            "member_details": self.member_details,
            "environment": env_name,
            "config_type": config_type
        }


class FirewallVipGroup(db.Model):
    __tablename__ = "firewall_vip_groups"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    name = db.Column(db.String(255), nullable=False)
    members = db.Column(db.Text)  # JSON array of VIP member names
    resolved_members = db.Column(db.Text)  # Pre-computed resolved member IPs (JSON)
    member_count = db.Column(db.Integer, default=0)  # Number of resolved members
    member_details = db.Column(db.Text(4294967295))  # LONGTEXT for detailed member info with names and IPs (JSON)
    created_at = db.Column(db.DateTime, default=utc_plus_8)

    # Relationships
    config_file = db.relationship('ConfigFile', backref='firewall_vip_groups')

    @property
    def serialize(self):
        env_name = "Unknown"
        config_type = "fortigate"  # VIP groups are FortiGate-specific
        if self.config_file:
            filename = self.config_file.filename

            if self.config_file.file_type == 'fw_prod':
                env_name = "Delta PROD FW"
            elif self.config_file.file_type == 'fw_admin':
                env_name = "Delta ADMIN FW"
            elif self.config_file.file_type == 'firewall':
                # Determine environment from filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'ADMIN-FW01' in filename:
                    env_name = "Admin FW"
                else:
                    env_name = "Firewall"

        return {
            "id": self.id,
            "name": self.name,
            "members": self.members,
            "resolved_members": self.resolved_members,
            "member_count": self.member_count,
            "member_details": self.member_details,
            "environment": env_name,
            "config_type": config_type,
            "object_type": "vip_group"
        }


class FirewallPolicy(db.Model):
    __tablename__ = "firewall_policies"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    policy_id = db.Column(db.String(50))
    name = db.Column(db.String(255))
    source_addresses = db.Column(db.Text)  # JSON array
    destination_addresses = db.Column(db.Text)  # JSON array
    source_zone = db.Column(db.String(100))  # Source interface/zone
    destination_zone = db.Column(db.String(100))  # Destination interface/zone
    services = db.Column(db.Text)  # JSON array
    action = db.Column(db.String(50))  # 'allow', 'deny'
    status = db.Column(db.String(50))  # 'enable', 'disable'
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='firewall_policies')
    
    @property
    def serialize(self):
        env_name = "Unknown"
        config_type = "unknown"
        if self.config_file:
            # Detect config type based on filename (Palo Alto files have ADMIN-FW01 pattern)
            filename = self.config_file.filename
            if 'ADMIN-FW01' in filename:
                config_type = "paloalto"
            else:
                config_type = "fortigate"
                
            if self.config_file.file_type == 'fw_prod':
                env_name = "Delta PROD FW"
            elif self.config_file.file_type == 'fw_admin':
                env_name = "Delta ADMIN FW"
            elif self.config_file.file_type == 'firewall':
                # Determine environment from filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'ADMIN-FW01' in filename:
                    env_name = "Admin FW"
                else:
                    env_name = "Firewall"
            
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "name": self.name,
            "source_addresses": self.source_addresses,
            "destination_addresses": self.destination_addresses,
            "source_zone": self.source_zone,
            "destination_zone": self.destination_zone,
            "services": self.services,
            "action": self.action,
            "status": self.status,
            "environment": env_name,
            "config_file_id": self.config_file_id,
            "config_type": config_type
        }


class FirewallNatPolicy(db.Model):
    __tablename__ = "firewall_nat_policies"
    id = db.Column(db.Integer, primary_key=True)
    config_file_id = db.Column(db.Integer, db.ForeignKey('config_files.id'))
    policy_id = db.Column(db.String(50))
    name = db.Column(db.String(255))
    status = db.Column(db.String(50))  # 'enable', 'disable'
    source_zone = db.Column(db.String(100))  # Source interface/zone
    destination_zone = db.Column(db.String(100))  # Destination interface/zone
    source_addresses = db.Column(db.Text)  # JSON array
    destination_addresses = db.Column(db.Text)  # JSON array
    services = db.Column(db.Text)  # JSON array
    source_translation = db.Column(db.Text)  # JSON object for source NAT translation
    destination_translation = db.Column(db.Text)  # JSON object for destination NAT translation
    tag = db.Column(db.String(100))  # Policy categorization/tag
    created_at = db.Column(db.DateTime, default=utc_plus_8)
    
    # Relationships
    config_file = db.relationship('ConfigFile', backref='firewall_nat_policies')
    
    @property
    def serialize(self):
        env_name = "Unknown"
        config_type = "unknown"
        if self.config_file:
            # Detect config type based on filename (Palo Alto files have ADMIN-FW01 pattern)
            filename = self.config_file.filename
            if 'ADMIN-FW01' in filename:
                config_type = "paloalto"
            else:
                config_type = "fortigate"
                
            if self.config_file.file_type == 'fw_prod':
                env_name = "Delta PROD FW"
            elif self.config_file.file_type == 'fw_admin':
                env_name = "Delta ADMIN FW"
            elif self.config_file.file_type == 'firewall':
                # Determine environment from filename
                if 'UAT-FW01' in filename:
                    env_name = "UAT FW"
                elif 'ALPHA-FW01' in filename:
                    env_name = "Alpha FW"
                elif 'BRAVO-FW01' in filename:
                    env_name = "Bravo FW"
                elif 'CHARLIE-FW01' in filename:
                    env_name = "Charlie FW"
                elif 'LoadTest-FW01' in filename:
                    env_name = "LoadTest FW"
                elif 'ADMIN-FW01' in filename:
                    env_name = "Admin FW"
                else:
                    env_name = "Firewall"
            
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "name": self.name,
            "status": self.status,
            "source_zone": self.source_zone,
            "destination_zone": self.destination_zone,
            "source_addresses": self.source_addresses,
            "destination_addresses": self.destination_addresses,
            "services": self.services,
            "source_translation": self.source_translation,
            "destination_translation": self.destination_translation,
            "tag": self.tag,
            "environment": env_name,
            "config_file_id": self.config_file_id,
            "config_type": config_type
        }


class SearchHistory(db.Model):
    __tablename__ = "search_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), nullable=False)  # Caller id (X-User-ID header, defaults to anonymous)
    search_query = db.Column(db.String(500), nullable=False)  # What was searched (IP, FQDN, object name)
    search_type = db.Column(db.String(50), nullable=False)  # 'ip', 'fqdn', 'object'
    search_date = db.Column(db.DateTime, default=utc_plus_8)
    results_count = db.Column(db.Integer, default=0)

    @property
    def serialize(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "search_query": self.search_query,
            "search_type": self.search_type,
            "search_date": self.search_date.strftime("%Y-%m-%d %H:%M:%S") if self.search_date else None,
            "results_count": self.results_count
        }



class DailyUpdateRun(db.Model):
    """One row per daily-update trigger, successful or not.

    Backs the update-history dashboard so a failed or missed run is visible
    rather than only living in the gunicorn log.
    """
    __tablename__ = "daily_update_runs"
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=utc_plus_8)
    finished_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Float)
    success = db.Column(db.Boolean, default=False)
    triggered_by = db.Column(db.String(50), default='manual')  # 'cron' or 'manual'
    files_downloaded = db.Column(db.Integer, default=0)
    files_expected = db.Column(db.Integer, default=0)
    files_parsed = db.Column(db.Integer, default=0)
    files_pruned = db.Column(db.Integer, default=0)
    bytes_freed = db.Column(db.BigInteger, default=0)
    message = db.Column(db.Text)

    @property
    def serialize(self):
        return {
            "id": self.id,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S") if self.started_at else None,
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else None,
            "duration_seconds": round(self.duration_seconds, 1) if self.duration_seconds else None,
            "success": self.success,
            "triggered_by": self.triggered_by,
            "files_downloaded": self.files_downloaded,
            "files_expected": self.files_expected,
            "files_parsed": self.files_parsed,
            "files_pruned": self.files_pruned,
            "bytes_freed": self.bytes_freed,
            "message": self.message
        }
