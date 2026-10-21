from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import requests
import os
from model import db, ConfigFile
from parsers.parser_service import ParserService
from blueprint.download.routes import ConfigDownloader

config_bp = Blueprint('config', __name__, url_prefix='/api/config')

def get_config_urls(date_obj=None):
    """Generate configuration file URLs with new server patterns"""
    if date_obj is None:
        # Get yesterday's date in GMT+8
        date_obj = datetime.utcnow() + timedelta(hours=8, days=-1)

    date_str = date_obj.strftime('%Y%m%d')
    base_url = f"{ConfigDownloader.BASE_URL.rstrip('/')}/DELTA_{date_str}"

    # All files now use 0500 timestamp
    urls = {
        'fw_prod': f"{base_url}/DELTA-FW01_{date_str}-0500.txt",
        'fw_admin': f"{base_url}/DELTA-ADMIN-FW01_{date_str}-0500.txt",
        'ltm': f"{base_url}/DELTA-LTM01_{date_str}-0500.txt"
    }

    return urls

@config_bp.route('/download', methods=['POST'])
def download_configs():
    """Download configuration files from the server"""
    try:
        # Create download directory if it doesn't exist
        download_dir = ConfigDownloader.DOWNLOAD_DIR
        os.makedirs(download_dir, exist_ok=True)
        
        urls = get_config_urls()
        downloaded_files = []
        
        for config_type, url in urls.items():
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Generate filename
                filename = url.split('/')[-1]
                file_path = os.path.join(download_dir, filename)
                
                # Save file
                with open(file_path, 'w') as f:
                    f.write(response.text)
                
                # Create database record
                config_file = ConfigFile(
                    filename=filename,
                    file_type=config_type,
                    file_path=file_path,
                    parsed_status='pending'
                )
                db.session.add(config_file)
                
                downloaded_files.append({
                    'type': config_type,
                    'filename': filename,
                    'url': url,
                    'status': 'downloaded'
                })
                
            except requests.exceptions.RequestException as e:
                downloaded_files.append({
                    'type': config_type,
                    'filename': None,
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Config download completed',
            'files': downloaded_files
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Download failed: {str(e)}'
        }), 500

@config_bp.route('/status', methods=['GET'])
def get_config_status():
    """Get status of configuration files"""
    try:
        # Get the latest file for each distinct configuration by extracting a unique key from filename
        from sqlalchemy import func, text
        
        # Create a unique key from the filename pattern (e.g., "DELTA-LTM01" -> "DELTA-LTM", "H2SLB01.TRZ.PRD" -> "H2SLB")
        config_files_raw = ConfigFile.query.order_by(ConfigFile.upload_date.desc()).all()
        
        # Get ALL files and deduplicate by filename to show all unique configurations
        # Remove time filtering to ensure we get all 15+ configurations
        
        # Deduplicate by configuration type (keep most recent of each config type)
        def get_config_type(filename):
            """Extract configuration type from filename"""
            if 'DELTA-FW01_' in filename:
                return 'DELTA-FW01'
            elif 'DELTA-ADMIN-FW01_' in filename:
                return 'DELTA-ADMIN-FW01'
            elif 'DELTA-LTM01_' in filename:
                return 'DELTA-LTM01'
            elif 'BRAVO-FW01_' in filename:
                return 'BRAVO-FW01'
            elif 'BRAVO-LTM01_' in filename:
                return 'BRAVO-LTM01'
            elif 'CHARLIE-FW01_' in filename:
                return 'CHARLIE-FW01'
            elif 'CHARLIE-LTM01_' in filename:
                return 'CHARLIE-LTM01'
            elif 'ALPHA-FW01_' in filename:
                return 'ALPHA-FW01'
            elif 'ALPHA-UAT-SLB01_' in filename:
                return 'ALPHA-UAT-SLB01'
            elif 'UAT-SLB01_' in filename:
                return 'UAT-SLB01'
            elif 'UAT-FW01_' in filename:
                return 'UAT-FW01'
            elif 'ADMIN-LTM01_' in filename:
                return 'ADMIN-LTM01'
            elif 'ADMIN-FW01_' in filename:
                return 'ADMIN-FW01'
            elif 'H2SLB01.TRZ.PRD_' in filename:
                return 'H2SLB01.TRZ.PRD'
            elif 'ALPHA-LTM01_' in filename:
                return 'ALPHA-LTM01'
            elif 'LoadTest-FW01_' in filename:
                return 'LoadTest-FW01'
            elif 'LoadTest-LTM01_' in filename:
                return 'LoadTest-LTM01'
            return filename.split('_')[0]  # fallback to prefix
        
        unique_configs = {}
        for file in config_files_raw:
            config_type = get_config_type(file.filename)
            if config_type not in unique_configs or file.upload_date > unique_configs[config_type].upload_date:
                unique_configs[config_type] = file
        
        # Convert back to list and sort by upload date (newest first)
        config_files = list(unique_configs.values())
        config_files.sort(key=lambda x: x.upload_date, reverse=True)
        
        files_data = []
        for file in config_files:
            file_data = {
                'filename': file.filename,
                'file_type': file.file_type,
                'status': file.parsed_status,
                'exists': os.path.exists(file.file_path) if file.file_path else False,
                'modified': file.upload_date.strftime("%Y-%m-%d %H:%M:%S") if file.upload_date else None,
                'source_url': file.source_url  # Return the stored source URL
            }
            
            # Add file size if file exists
            if file.file_path and os.path.exists(file.file_path):
                try:
                    file_data['size'] = os.path.getsize(file.file_path)
                except Exception:
                    file_data['size'] = None
            else:
                file_data['size'] = None
                
            files_data.append(file_data)
        
        return jsonify({
            'success': True,
            'files': files_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to get config status: {str(e)}'
        }), 500

@config_bp.route('/urls', methods=['GET'])
def get_current_urls():
    """Get current configuration file URLs"""
    try:
        urls = get_config_urls()
        return jsonify({
            'success': True,
            'urls': urls,
            'date': datetime.utcnow().strftime('%Y-%m-%d')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to generate URLs: {str(e)}'
        }), 500

@config_bp.route('/parse', methods=['POST'])
def parse_configs():
    """Parse all pending configuration files"""
    try:
        results = ParserService.parse_all_pending()
        
        return jsonify({
            'success': True,
            'message': 'Config parsing completed',
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Parsing failed: {str(e)}'
        }), 500

@config_bp.route('/parse/<int:file_id>', methods=['POST'])
def parse_single_config(file_id):
    """Parse a specific configuration file"""
    try:
        result = ParserService.parse_config_file(file_id)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Parsing failed: {str(e)}'
        }), 500