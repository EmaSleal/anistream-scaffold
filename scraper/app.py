from flask import Flask
from routes.health_routes import health_bp
from routes.ingest_routes import bp
from routes.series_routes import series_bp
from routes.episode_routes import episode_bp
from routes.watchlist_routes import watchlist_bp
from routes.progress_routes import progress_bp
from routes.auth_routes import auth_bp
from routes.simulcast_routes import simulcast_bp
from routes.stream_proxy_routes import stream_proxy_bp
from routes.downloads_routes import downloads_bp
from scheduler import init_scheduler


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
    app.register_blueprint(stream_proxy_bp)
    app.register_blueprint(downloads_bp)

    scheduler = init_scheduler(app)
    if scheduler is not None:
        app.extensions["scheduler"] = scheduler

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
