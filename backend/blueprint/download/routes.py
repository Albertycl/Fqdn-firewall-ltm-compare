import os
import re
import sys
import subprocess
import time
import requests
import pytz
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from model import db, ConfigFile, DailyUpdateRun
from parsers.parser_service import ParserService
from services.database_cleanup import DatabaseCleanupService

def log(msg):
    """Print progress with timestamp, flush immediately for gunicorn"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _now_gmt8():
    return datetime.now(pytz.timezone('Asia/Singapore')).replace(tzinfo=None)


def _record_run(started_at, started_ts, success, message, triggered_by='manual',
                downloaded=0, expected=0, parsed=0, pruned=0, freed=0):
    """Persist one daily-update attempt.

    Never raises: failing to write history must not turn a good run into a bad
    one, so any error here is logged and swallowed.
    """
    try:
        run = DailyUpdateRun(
            started_at=started_at,
            finished_at=_now_gmt8(),
            duration_seconds=time.time() - started_ts,
            success=success,
            triggered_by=triggered_by,
            message=(message or '')[:60000] or None,
            files_downloaded=downloaded,
            files_expected=expected,
            files_parsed=parsed,
            files_pruned=pruned,
            bytes_freed=freed,
        )
        db.session.add(run)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log(f"  WARN: could not record run history: {e}")


download_bp = Blueprint('download', __name__, url_prefix='/api/download')

class ConfigDownloader:
    """Service class for downloading network configuration files"""

    # Both are environment-driven so the app carries no host- or path-specific
    # values. The defaults reproduce the original deployment.
    BASE_URL = os.getenv('CONFIG_SOURCE_URL', 'http://config-server.example/configs/')
    DOWNLOAD_DIR = os.getenv(
        'DOWNLOAD_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), '..', 'download')
    )
    DOWNLOAD_DIR = os.path.abspath(DOWNLOAD_DIR) + os.sep

    # File configurations with their URL patterns and timestamps
    FILE_CONFIGS = {
        # Core Delta configs (now all use 0500 timestamp)
        'delta_fw_prod': {
            'url_pattern': 'DELTA_{date}/DELTA-FW01_{date}-0500.txt',
            'file_type': 'fw_prod'
        },
        'delta_fw_admin': {
            'url_pattern': 'DELTA_{date}/DELTA-ADMIN-FW01_{date}-0500.txt',
            'file_type': 'fw_admin'
        },
        'delta_ltm': {
            'url_pattern': 'DELTA_{date}/DELTA-LTM01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        # Additional LTM sources (simplified patterns without yearmonth)
        'charlie_ltm': {
            'url_pattern': 'CHARLIE_{date}/CHARLIE-LTM01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        'bravo_ltm': {
            'url_pattern': 'BRAVO_{date}/BRAVO-LTM01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        'alpha_ltm': {
            'url_pattern': 'ALPHA_{date}/ALPHA-LTM01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        'admin_ltm': {
            'url_pattern': 'ADMIN_{date}/ADMIN-LTM01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        'uat_slb': {
            'url_pattern': 'UAT_{date}/UAT-SLB01_{date}-0500.txt',
            'file_type': 'ltm'
        },
        # Additional Firewall sources (simplified patterns without yearmonth)
        'alpha_fw': {
            'url_pattern': 'ALPHA_{date}/ALPHA-FW01_{date}-0500.txt',
            'file_type': 'firewall'
        },
        'uat_fw': {
            'url_pattern': 'UAT_{date}/UAT-FW01_{date}-0500.txt',
            'file_type': 'firewall'
        },
        'bravo_fw': {
            'url_pattern': 'BRAVO_{date}/BRAVO-FW01_{date}-0500.txt',
            'file_type': 'firewall'
        },
        'charlie_fw': {
            'url_pattern': 'CHARLIE_{date}/CHARLIE-FW01_{date}-0500.txt',
            'file_type': 'firewall'
        },
        'admin_fw': {
            'url_pattern': 'ADMIN_{date}/ADMIN-FW01_{date}-0500.txt',
            'file_type': 'firewall'
        },
    }

    # Decommissioned sites: no longer backed up on the config server
    # (no longer published).
    # The daily update skips these so it doesn't fail on missing files. Their
    # already-parsed data is preserved on cleanup so it stays searchable.
    DECOMMISSIONED_CONFIG_KEYS = ('charlie_ltm', 'charlie_fw', 'bravo_ltm', 'bravo_fw')
    DECOMMISSIONED_SITE_PREFIXES = ('CHARLIE-', 'BRAVO-')

    @classmethod
    def active_config_items(cls):
        """FILE_CONFIGS entries for infra still being backed up.

        Excludes decommissioned sites (Charlie/Bravo) so the daily update only
        downloads sources that actually exist on the config server.
        """
        return {k: v for k, v in cls.FILE_CONFIGS.items()
                if k not in cls.DECOMMISSIONED_CONFIG_KEYS}

    # Every daily run re-downloads the configs it needs, so only the dates the
    # today->yesterday fallback can still reach are worth keeping on disk. Older
    # files are already parsed into the database; without this the directory grew
    # without bound (1,956 files, ~1 GB, before retention was added).
    RETENTION_DAYS = 2
    _DATED_FILE_RE = re.compile(r'_(\d{8})-\d{4}\.txt$')

    @classmethod
    def prune_old_downloads(cls, retention_days=None):
        """Delete downloaded configs older than the retention window.

        Only files whose name carries a YYYYMMDD stamp are considered, so undated
        assets in the directory are left alone. Call this *after* parsing so a
        file is never removed before it has been read into the database.

        Returns:
            dict: {'deleted': int, 'freed_bytes': int, 'kept_dates': [...], 'errors': [...]}
        """
        retention_days = cls.RETENTION_DAYS if retention_days is None else retention_days
        keep_dates = {cls.get_date_for_day_offset(i)['date'] for i in range(retention_days)}
        cutoff = min(keep_dates)

        deleted, freed, errors = 0, 0, []
        if not os.path.isdir(cls.DOWNLOAD_DIR):
            return {'deleted': 0, 'freed_bytes': 0, 'kept_dates': sorted(keep_dates), 'errors': []}

        for name in os.listdir(cls.DOWNLOAD_DIR):
            match = cls._DATED_FILE_RE.search(name)
            if not match or match.group(1) >= cutoff:
                continue  # undated asset, or within the retention window
            path = os.path.join(cls.DOWNLOAD_DIR, name)
            try:
                size = os.path.getsize(path)
                os.remove(path)
                deleted += 1
                freed += size
            except OSError as e:
                errors.append(f"{name}: {e}")

        return {
            'deleted': deleted,
            'freed_bytes': freed,
            'kept_dates': sorted(keep_dates),
            'errors': errors,
        }

    @staticmethod
    def get_date_for_day_offset(days_offset=0):
        """
        Get date info for a specific day offset from today in GMT+8 timezone

        Args:
            days_offset (int): Days to subtract from today (0=today, 1=yesterday)

        Returns:
            dict: {'date': 'YYYYMMDD'}
        """
        gmt8 = pytz.timezone('Asia/Singapore')  # GMT+8
        now_gmt8 = datetime.now(gmt8)
        target_date = now_gmt8 - timedelta(days=days_offset)
        return {
            'date': target_date.strftime('%Y%m%d')  # YYYYMMDD
        }

    @classmethod
    def get_date_candidates(cls):
        """
        Get list of date candidates to try (today, then yesterday)

        Returns:
            list: [today_date_info, yesterday_date_info]
        """
        return [
            cls.get_date_for_day_offset(0),  # Today
            cls.get_date_for_day_offset(1)   # Yesterday
        ]

    @classmethod
    def get_yesterday_date(cls):
        """Get yesterday's date in GMT+8 timezone (legacy method for compatibility)"""
        return cls.get_date_for_day_offset(1)

    @classmethod
    def build_url(cls, url_pattern, date_info):
        """Build full URL from pattern and date info"""
        # New server only uses {date}, not {yearmonth}
        url_path = url_pattern.format(date=date_info['date'])
        return cls.BASE_URL + url_path
    
    @staticmethod
    def download_file(url, local_path):
        """Download a file from URL to local path with error handling"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Write file content
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(response.text)

            return True, None
        except requests.RequestException as e:
            return False, f"Download failed: {str(e)}"
        except Exception as e:
            return False, f"File write failed: {str(e)}"

    @classmethod
    def validate_file_with_fallback(cls, config_name, config):
        """
        Validate a single config file with date fallback (today -> yesterday)

        Args:
            config_name (str): Configuration identifier
            config (dict): Configuration with url_pattern and file_type

        Returns:
            dict: Validation result with date_used, url, accessible status
        """
        date_candidates = cls.get_date_candidates()

        for idx, date_info in enumerate(date_candidates):
            date_label = 'today' if idx == 0 else 'yesterday'

            # Build URL from pattern
            file_url = cls.build_url(config['url_pattern'], date_info)
            filename = file_url.split('/')[-1]

            try:
                # Use HEAD request to check if file exists
                response = requests.head(file_url, timeout=10)

                if response.status_code == 200:
                    return {
                        'config_name': config_name,
                        'filename': filename,
                        'url': file_url,
                        'date_used': date_label,
                        'accessible': True,
                        'error': None,
                        'date_info': date_info
                    }
            except requests.RequestException as e:
                last_error = str(e)
                continue

        # Both dates failed
        return {
            'config_name': config_name,
            'filename': filename,
            'url': file_url,
            'date_used': None,
            'accessible': False,
            'error': f'Not accessible for today or yesterday',
            'date_info': None
        }

    @classmethod
    def validate_all_files_accessible(cls):
        """Validate all files with per-file date fallback"""
        validation_results = []
        all_accessible = True

        for config_name, config in cls.active_config_items().items():
            result = cls.validate_file_with_fallback(config_name, config)
            validation_results.append(result)

            if not result['accessible']:
                all_accessible = False

        return all_accessible, validation_results
    
    @staticmethod
    def store_config_file(filename, file_path, file_type, source_url=None):
        """Store config file information in database with source URL tracking"""
        try:
            # Check if config file already exists for today
            existing_file = ConfigFile.query.filter_by(
                filename=filename,
                file_type=file_type
            ).first()

            if existing_file:
                # Update existing record
                existing_file.file_path = file_path
                existing_file.parsed_status = 'pending'
                existing_file.upload_date = datetime.utcnow()
                if source_url:
                    existing_file.source_url = source_url
            else:
                # Create new record
                config_file = ConfigFile(
                    filename=filename,
                    file_path=file_path,
                    file_type=file_type,
                    source_url=source_url,
                    parsed_status='pending'
                )
                db.session.add(config_file)

            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, f"Database storage failed: {str(e)}"
    
    @classmethod
    def download_all_files(cls, validation_results=None):
        """
        Download all configuration files using pre-validated results

        Args:
            validation_results (list): Pre-validated results with URLs and dates

        Returns:
            tuple: (results, successful_files)
        """
        results = []
        successful_files = []

        # If no validation results provided, validate first
        if validation_results is None:
            _, validation_results = cls.validate_all_files_accessible()

        for validation_result in validation_results:
            config_name = validation_result['config_name']
            config = cls.FILE_CONFIGS[config_name]

            # Skip if file not accessible
            if not validation_result['accessible']:
                results.append({
                    'config_name': config_name,
                    'filename': validation_result['filename'],
                    'url': validation_result['url'],
                    'date_used': None,
                    'local_path': None,
                    'download_success': False,
                    'error': validation_result['error'],
                    'db_success': False
                })
                continue

            # Use validated URL and date
            file_url = validation_result['url']
            filename = validation_result['filename']
            date_used = validation_result['date_used']
            local_path = os.path.join(cls.DOWNLOAD_DIR, filename)

            # Download file
            success, error = cls.download_file(file_url, local_path)

            result = {
                'config_name': config_name,
                'filename': filename,
                'url': file_url,
                'date_used': date_used,
                'local_path': local_path,
                'download_success': success,
                'error': error
            }

            if success:
                # Store in database with source_url
                db_success, db_error = cls.store_config_file(
                    filename=filename,
                    file_path=local_path,
                    file_type=config['file_type'],
                    source_url=file_url
                )
                result['db_success'] = db_success
                result['db_error'] = db_error

                if db_success:
                    successful_files.append({
                        'filename': filename,
                        'file_type': config['file_type'],
                        'date_used': date_used
                    })

            results.append(result)

        return results, successful_files

@download_bp.route('/daily', methods=['GET'])
def download_daily_configs():
    """Download all daily configuration files with per-file date fallback"""
    try:
        start_time = time.time()
        run_started_at = _now_gmt8()
        # 'cron' when the scheduled job calls us, 'manual' from the UI or by hand
        triggered_by = request.args.get('triggered_by', 'manual')
        total_configs = len(ConfigDownloader.active_config_items())
        log(f"=== Daily Update Started ({total_configs} active configs, "
            f"skipping decommissioned: {', '.join(ConfigDownloader.DECOMMISSIONED_CONFIG_KEYS)}) ===")

        # Step 1: Validate all files with per-file fallback
        log("Step 1/4: Validating file accessibility...")
        all_accessible, validation_results = ConfigDownloader.validate_all_files_accessible()

        # Build date summary for transparency
        date_summary = {
            'today': sum(1 for r in validation_results if r.get('date_used') == 'today'),
            'yesterday': sum(1 for r in validation_results if r.get('date_used') == 'yesterday'),
            'failed': sum(1 for r in validation_results if not r['accessible'])
        }
        log(f"  Validation done: {date_summary['today']} today, {date_summary['yesterday']} yesterday, {date_summary['failed']} failed")

        if not all_accessible:
            failed_files = [r['config_name'] for r in validation_results if not r['accessible']]
            log(f"  FAILED files: {', '.join(failed_files)}")
            _record_run(run_started_at, start_time, False,
                        f"Validation failed: {', '.join(failed_files)}",
                        triggered_by=triggered_by, expected=total_configs)
            return jsonify({
                'success': False,
                'message': f"Not all files accessible. {date_summary['failed']} file(s) failed.",
                'date_summary': date_summary,
                'validation_results': validation_results
            }), 400

        # Step 2: Download using validated results
        log("Step 2/4: Downloading files...")
        results, successful_files = ConfigDownloader.download_all_files(validation_results)

        # Count successes
        download_successes = sum(1 for r in results if r['download_success'])
        db_successes = sum(1 for r in results if r.get('db_success', False))
        log(f"  Downloaded {download_successes}/{total_configs}, DB stored {db_successes}/{total_configs}")

        # Step 3: Only proceed with parsing if all successful
        if download_successes == total_configs and db_successes == total_configs:
            response = {
                'success': True,
                'message': f'Downloaded {download_successes}/{total_configs} files, {db_successes}/{total_configs} in database',
                'date_summary': date_summary,
                'results': results,
                'successful_files': successful_files,
                'validation_results': validation_results
            }

            # Auto-parse if requested
            auto_parse = request.args.get('auto_parse', 'true').lower() == 'true'
            if auto_parse and successful_files:
                log("Step 3/4: Cleaning up old parsed data (preserving decommissioned sites)...")
                cleanup_result = DatabaseCleanupService.clear_parsed_data_except(
                    ConfigDownloader.DECOMMISSIONED_SITE_PREFIXES
                )
                response['cleanup_result'] = cleanup_result
                log(f"  Cleanup: {cleanup_result['message']}")

                if cleanup_result['success']:
                    log("Step 4/5: Parsing config files...")
                    parse_results = ParserService.parse_all_pending()
                    response['parse_results'] = parse_results
                    response['message'] += f', parsed {len(parse_results)} files'

                    # Prune only after a successful parse, so a config is never
                    # removed from disk before it has been read into the database.
                    log(f"Step 5/5: Pruning downloads older than "
                        f"{ConfigDownloader.RETENTION_DAYS} day(s)...")
                    prune_result = ConfigDownloader.prune_old_downloads()
                    response['prune_result'] = prune_result
                    log(f"  Pruned {prune_result['deleted']} file(s), "
                        f"freed {prune_result['freed_bytes'] / 1048576:.1f} MB "
                        f"(kept {', '.join(prune_result['kept_dates'])})")
                    if prune_result['errors']:
                        log(f"  Prune errors: {'; '.join(prune_result['errors'][:3])}")

            elapsed = time.time() - start_time
            log(f"=== Daily Update Complete in {elapsed:.1f}s ===")
            prune = response.get('prune_result') or {}
            _record_run(run_started_at, start_time, True, response['message'],
                        triggered_by=triggered_by,
                        downloaded=download_successes, expected=total_configs,
                        parsed=len(response.get('parse_results') or []),
                        pruned=prune.get('deleted', 0),
                        freed=prune.get('freed_bytes', 0))
            return jsonify(response)
        else:
            failed = [r['config_name'] for r in results if not r['download_success']]
            log(f"  FAILED downloads: {', '.join(failed)}")
            _record_run(run_started_at, start_time, False,
                        f"Partial failure, failed downloads: {', '.join(failed)}",
                        triggered_by=triggered_by,
                        downloaded=download_successes, expected=total_configs)
            return jsonify({
                'success': False,
                'message': f'Partial failure: {download_successes}/{total_configs} downloaded',
                'date_summary': date_summary,
                'results': results
            }), 500

    except Exception as e:
        log(f"  ERROR: {str(e)}")
        # start_time/run_started_at exist unless the failure was immediate
        try:
            _record_run(run_started_at, start_time, False, f"Error: {e}",
                        triggered_by=locals().get('triggered_by', 'manual'))
        except NameError:
            pass
        return jsonify({
            'success': False,
            'message': f'Download failed: {str(e)}'
        }), 500


def _schedule_info():
    """When the daily update is scheduled to run next.

    Reads the real crontab so the dashboard cannot drift from what is actually
    scheduled; falls back to DAILY_UPDATE_HOUR/MINUTE if no entry is found.
    """
    hour, minute, source = None, None, 'none'
    try:
        out = subprocess.run(['crontab', '-l'], capture_output=True,
                             text=True, timeout=5).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('#') or 'download/daily' not in line:
                continue
            fields = line.split()
            if len(fields) >= 5 and fields[0].isdigit() and fields[1].isdigit():
                minute, hour, source = int(fields[0]), int(fields[1]), 'crontab'
                break
    except Exception:
        pass

    if hour is None:
        hour = int(os.getenv('DAILY_UPDATE_HOUR', 6))
        minute = int(os.getenv('DAILY_UPDATE_MINUTE', 0))
        source = 'default'

    now = _now_gmt8()
    nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)

    return {
        'scheduled': source != 'none',
        'source': source,
        'time_of_day': f'{hour:02d}:{minute:02d}',
        'next_run': nxt.strftime('%Y-%m-%d %H:%M:%S'),
        'seconds_until': int((nxt - now).total_seconds()),
        'timezone': 'GMT+8',
    }


@download_bp.route('/schedule', methods=['GET'])
def daily_update_schedule():
    """The active schedule and next fire time."""
    try:
        return jsonify({'success': True, 'schedule': _schedule_info()})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to read schedule: {e}'}), 500


@download_bp.route('/history', methods=['GET'])
def daily_update_history():
    """Recent daily-update runs, newest first, for the update dashboard."""
    try:
        limit = min(int(request.args.get('limit', 50)), 500)
        runs = (DailyUpdateRun.query
                .order_by(DailyUpdateRun.started_at.desc())
                .limit(limit).all())
        return jsonify({
            'success': True,
            'runs': [r.serialize for r in runs],
            'count': len(runs),
            'schedule': _schedule_info(),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to load history: {e}'}), 500


@download_bp.route('/log', methods=['GET'])
def daily_update_log():
    """Tail of the cron log, for the update dashboard.

    The path is fixed (env-overridable) rather than taken from the request, so
    this cannot be used to read arbitrary files. Output is capped so a large log
    never floods the response.
    """
    log_path = os.getenv(
        'DAILY_UPDATE_LOG',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), 'daily_update.log')
    )
    try:
        lines = min(int(request.args.get('lines', 200)), 2000)
    except ValueError:
        lines = 200

    if not os.path.isfile(log_path):
        return jsonify({
            'success': True,
            'exists': False,
            'path': log_path,
            'content': '',
            'message': 'No log yet — the scheduled job has not run.'
        })

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            tail = f.readlines()[-lines:]
        stat = os.stat(log_path)
        return jsonify({
            'success': True,
            'exists': True,
            'path': log_path,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'lines': len(tail),
            'content': ''.join(tail),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to read log: {e}'}), 500


@download_bp.route('/status', methods=['GET'])
def download_status():
    """Get status of recent downloads"""
    try:
        date_info = ConfigDownloader.get_yesterday_date()

        # Check which files exist locally
        local_files = []
        for config_name, config in ConfigDownloader.FILE_CONFIGS.items():
            # Build URL from pattern to extract filename
            file_url = ConfigDownloader.build_url(config['url_pattern'], date_info)
            filename = file_url.split('/')[-1]
            local_path = os.path.join(ConfigDownloader.DOWNLOAD_DIR, filename)
            
            exists = os.path.exists(local_path)
            file_info = {
                'config_name': config_name,
                'filename': filename,
                'exists': exists,
                'file_type': config['file_type']
            }
            
            if exists:
                stat = os.stat(local_path)
                file_info['size'] = stat.st_size
                file_info['modified'] = datetime.fromtimestamp(stat.st_mtime).isoformat()
            
            local_files.append(file_info)
        
        # Check database status
        db_files = []
        for config_name, config in ConfigDownloader.FILE_CONFIGS.items():
            # Build URL from pattern to extract filename
            file_url = ConfigDownloader.build_url(config['url_pattern'], date_info)
            filename = file_url.split('/')[-1]
            config_file = ConfigFile.query.filter_by(
                filename=filename,
                file_type=config['file_type']
            ).first()

            db_info = {
                'config_name': config_name,
                'filename': filename,
                'in_database': config_file is not None
            }

            if config_file:
                db_info['parsed_status'] = config_file.parsed_status
                db_info['upload_date'] = config_file.upload_date.isoformat() if config_file.upload_date else None

            db_files.append(db_info)
        
        # Combine local and database info for frontend
        combined_files = []
        for local_file in local_files:
            # Find corresponding database file
            db_file = next(
                (db for db in db_files if db['filename'] == local_file['filename']), 
                None
            )
            
            file_info = {
                'filename': local_file['filename'],
                'config_name': local_file['config_name'],
                'file_type': local_file['file_type'],
                'exists': local_file['exists'],
                'status': 'parsed' if (db_file and db_file.get('parsed_status') == 'parsed') else 'pending'
            }
            
            if local_file['exists']:
                file_info['size'] = local_file['size']
                file_info['modified'] = local_file['modified']
            
            combined_files.append(file_info)
        
        return jsonify({
            'success': True,
            'date': date_info['date'],
            'files': combined_files,
            'local_files': local_files,
            'database_files': db_files
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Status check failed: {str(e)}'
        }), 500

@download_bp.route('/test-connection', methods=['GET'])
def test_connection():
    """Test connection to file server"""
    try:
        # Probe a URL the daily update actually fetches, rather than a fixed
        # guess: an unreachable server and a wrong path are different faults and
        # must not both report success.
        config = ConfigDownloader.FILE_CONFIGS['delta_fw_prod']
        for offset in (0, 1):
            date_info = ConfigDownloader.get_date_for_day_offset(offset)
            test_url = ConfigDownloader.BASE_URL + config['url_pattern'].format(
                date=date_info['date'])
            response = requests.head(test_url, timeout=10)
            if response.status_code < 400:
                return jsonify({
                    'success': True,
                    'message': f"Connection successful ({'today' if offset == 0 else 'yesterday'})",
                    'date': date_info['date'],
                    'base_url': test_url,
                    'status_code': response.status_code
                })

        # Reachable but nothing to download: a real problem the daily run will hit.
        return jsonify({
            'success': False,
            'message': f'Server reachable but no config found (HTTP {response.status_code})',
            'date': date_info['date'],
            'base_url': test_url,
            'status_code': response.status_code
        }), 502

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Connection failed: {str(e)}',
            'date': ConfigDownloader.get_yesterday_date()['date']
        }), 500