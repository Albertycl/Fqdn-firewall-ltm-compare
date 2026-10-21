from sqlalchemy import or_
from model import db, LtmVirtualServer, LtmPool, LtmNode, FirewallAddressObject, FirewallAddressGroup, FirewallPolicy, FirewallNatPolicy, ConfigFile

class DatabaseCleanupService:
    """Service for safely clearing database data before fresh imports"""

    @staticmethod
    def clear_all_parsed_data():
        """Clear all parsed data from all tables but keep config file records"""
        try:
            # Delete in proper order to respect foreign key constraints
            # LtmNode has FK to both config_file and pool, so delete first
            db.session.query(LtmNode).delete()
            
            # Delete LTM pools (after nodes are deleted)
            db.session.query(LtmPool).delete()
            
            # Delete LTM virtual servers
            db.session.query(LtmVirtualServer).delete()
            
            # Delete firewall data
            db.session.query(FirewallNatPolicy).delete()
            db.session.query(FirewallPolicy).delete()
            db.session.query(FirewallAddressGroup).delete()
            db.session.query(FirewallAddressObject).delete()
            
            # Don't reset old config files - only today's downloads will be set to 'pending' by the download step
            
            # Commit all changes
            db.session.commit()
            
            return {
                'success': True,
                'message': 'All parsed data cleared successfully'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': f'Database cleanup failed: {str(e)}'
            }
    
    @staticmethod
    def clear_parsed_data_except(preserve_filename_prefixes=None):
        """Clear parsed data before a fresh import, but preserve rows belonging
        to config files whose filename starts with one of the given prefixes.

        Used by the daily update to refresh active infra while keeping the last
        parsed config of decommissioned sites (e.g. CHARLIE-, BRAVO-) searchable.
        Config file records themselves are left untouched.
        """
        preserve_filename_prefixes = list(preserve_filename_prefixes or [])
        try:
            # Resolve the config_file ids we must keep
            preserve_ids = set()
            if preserve_filename_prefixes:
                conds = [ConfigFile.filename.like(f"{p}%") for p in preserve_filename_prefixes]
                preserved = ConfigFile.query.filter(or_(*conds)).all()
                preserve_ids = {c.id for c in preserved}

            def _delete_except(model):
                q = model.query
                if preserve_ids:
                    q = q.filter(~model.config_file_id.in_(preserve_ids))
                q.delete(synchronize_session=False)

            # Same FK-safe order as clear_all_parsed_data: nodes -> pools -> VS
            _delete_except(LtmNode)
            _delete_except(LtmPool)
            _delete_except(LtmVirtualServer)
            _delete_except(FirewallNatPolicy)
            _delete_except(FirewallPolicy)
            _delete_except(FirewallAddressGroup)
            _delete_except(FirewallAddressObject)

            db.session.commit()
            return {
                'success': True,
                'message': (f'Parsed data cleared, preserved {len(preserve_ids)} '
                            f'config file(s) for prefixes {preserve_filename_prefixes}')
            }
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': f'Scoped cleanup failed: {str(e)}'
            }

    @staticmethod
    def get_data_counts():
        """Get current count of records in all tables for verification"""
        try:
            counts = {
                'config_files': db.session.query(ConfigFile).count(),
                'ltm_virtual_servers': db.session.query(LtmVirtualServer).count(),
                'ltm_pools': db.session.query(LtmPool).count(),
                'ltm_nodes': db.session.query(LtmNode).count(),
                'firewall_address_objects': db.session.query(FirewallAddressObject).count(),
                'firewall_address_groups': db.session.query(FirewallAddressGroup).count(),
                'firewall_policies': db.session.query(FirewallPolicy).count(),
                'firewall_nat_policies': db.session.query(FirewallNatPolicy).count()
            }
            return {'success': True, 'counts': counts}
        except Exception as e:
            return {'success': False, 'message': f'Count query failed: {str(e)}'}