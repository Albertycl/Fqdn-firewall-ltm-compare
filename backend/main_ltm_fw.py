import warnings
warnings.filterwarnings('ignore', message='urllib3.*or chardet.*doesn\'t match')
import os
#########Migrations#############
from flask import Flask, jsonify
from blueprint.config.routes import config_bp
from blueprint.search.routes import search_bp
from blueprint.download.routes import download_bp



#########Migrations#############
from model import db
from flask_cors import CORS
from flask_migrate import Migrate
from config import DevConfig

app = Flask(__name__)
app.config.from_object(DevConfig)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
CORS(app)

# Register blueprints
app.register_blueprint(config_bp)
app.register_blueprint(search_bp)
app.register_blueprint(download_bp)

@app.route('/')
def index():
    return jsonify({
        'message': 'Network Configuration Portal API',
        'version': '1.0',
        'endpoints': {
            'config': '/api/config/',
            'search': '/api/search/',
            'download': '/api/download/'
        }
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=os.getenv('FLASK_DEBUG') == '1', host='0.0.0.0', port=5432)
