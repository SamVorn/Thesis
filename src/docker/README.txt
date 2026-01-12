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
