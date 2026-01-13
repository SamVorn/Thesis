remove old container
> docker ps -a
> docker rm -f thesis-mongo

stop existing container
> docker stop [name]

docker compose 
> docker-compose up -d
> tells Docker to read the docker-compose.yml file
> up starts the services
> -d runs them detached

checking if container is running
> docker ps

seed_mongo.py
> setup and initialization script for MongoDB
> creates database
> inserts sample survey templates into surveys collection
> inserts sample survey responses into responses collection

testing connectivity using mongo shell
> docker exec -it thesis-mongo mongosh
- when inside mongosh you can check if collections exist
> show collections
> db.responses.find().pretty()
- when container is running and using mongo shell
> use thesis_pipeline
> show collections
> db.surveys.find().pretty()

to run the mongo test pipeline
> python -m src.tests.test_mongo_pipeline
> in powershell

1. start docker
2. connect to mongodb shell
3. seed mongodb
4. test pipeline

SQL Stuff
> build docker container as said, don't need to seed the mongoDB stuff
> docker exec -i thesis_postgres psql -U thesis -d thesis_pipeline < sql_schema.sql
to create SQL tables
> run: python seed_sql.py to seed the sql database for testing

docker compose up -d
docker exec -i thesis_postgres psql -U thesis -d thesis_pipeline < sql_schema.sql
or
Get-Content sql_schema.sql | docker exec -i thesis_postgres psql -U thesis -d thesis_pipeline
python seed_sql.py
python -m src.tests.test_sql_pipeline






SQLAlchemy abstracts the SQL dialects

Your queries use parameterized SQL via text(...) and :param style bindings.

SQLAlchemy will translate this into the correct syntax for Postgres, MySQL, SQLite, MariaDB, etc.

No engine-specific code in the adapter

get_survey_template, iter_responses, save_flags just use engine.connect() and conn.execute(text(query), params).

No Postgres-only functions, no SQLite-only hacks.

Table names are passed in dynamically

table_names dict lets you point to different table structures, so you can reuse the same adapter for multiple SQL DBs.