web: gunicorn search_engine.asgi:application -k search_engine.workers.DynamicUvicornWorker --timeout 500
worker: celery -A search_engine worker -B -Q celery -l info -E --scheduler django_celery_beat.schedulers:DatabaseScheduler --without-gossip --without-mingle --without-heartbeat
