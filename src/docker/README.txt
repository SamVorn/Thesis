Current pipeline usage 3/2/26
    python seed.py --db both
    >> Basic seeding both DBs with 100 responses
    python seed.py --db mongo --count 50 --model mistral
    >> Custom count + model
    python seed.py --db sql --reset
    >> Reset existing data first
    >> Nuclear option to just compose down Docker containers
    python seed.py --db both --ollama-url http://192.168.1.10:11434
    >> Use a remote Ollama instance

testing connectivity using mongo shell
    > docker exec -it thesis-mongo mongosh
    > use thesis_pipeline
    > db.responses.find().pretty()
    > show collections
    > db.surveys.find().pretty()
    -- can add limiter to reduce the amount of surveys shown

SQL Usage
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
    docker exec -it thesis_postgres psql -U thesis -d thesis_pipeline
    SELECT * FROM survey_templates;
    SELECT * FROM survey_responses LIMIT 5;

docker usage
    docker-compose down -v
    >> to completely remove docker containers networks and volumes
    docker ps -a
    >> remove old container
    docker stop [name]
    >> stop existing container
    docker-compose up -d
    >> tells Docker to read the docker-compose.yml file
    >> up starts the services
    >> -d runs them detached
    checking if container is running
    > docker ps

Ollama Usage:
    python seed.py --db both        # seed MongoDB and Postgres
    python seed.py --db mongo       # seed MongoDB only
    python seed.py --db sql         # seed Postgres only

    --survey-id   custom survey ID (default: survey1)
    --count       number of responses to generate (default: 100)
    --model       Ollama model to use (default: llama3)
    --reset       drop/clear existing data before seeding

test_pipeline usage
    python test_pipeline.py  
    >> will prompt you to pick a db   
    python test_pipeline.py --source mongo
    python test_pipeline.py --source sql
    python test_pipeline.py --source file
    python test_pipeline.py --source mongo --no-confirm   
    >> no-confirm skips confirmation duh

Outdated
    to run the mongo test pipeline
    > python -m src.tests.test_mongo_pipeline
    > in powershell

    1. start docker
    2. connect to mongodb shell
    3. seed mongodb
    4. test pipeline
    seed_mongo.py
    > setup and initialization script for MongoDB
    > creates database
    > inserts sample survey templates into surveys collection
    > inserts sample survey responses into responses collection