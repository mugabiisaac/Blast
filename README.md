# How to start

Set up and configure virtalenv

`virtualenv -p python3 env`

`. env/bin/activate`

`pip install --upgrade pip`

`pip install -r conf/requriments.txt`

Load fixtures

`./manage.py loaddata countries`

Start dev-server

`./manage.py runserver 0.0.0.0:8000`
