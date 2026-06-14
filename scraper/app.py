from flask import Flask
from routes.health_routes import health_bp
from routes.ingest_routes import bp
from routes.series_routes import series_bp
from routes.episode_routes import episode_bp
from routes.watchlist_routes import watchlist_bp
from routes.progress_routes import progress_bp
from routes.auth_routes import auth_bp
from routes.simulcast_routes import simulcast_bp
from routes.transcode_routes import transcode_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(health_bp)
    app.register_blueprint(bp, url_prefix="/api")
    app.register_blueprint(series_bp)
    app.register_blueprint(episode_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(simulcast_bp)
    app.register_blueprint(transcode_bp)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
