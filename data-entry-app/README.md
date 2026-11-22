# Data Entry App (Flask + MongoDB + Docker)

## Run (recommended)
    docker compose up --build -d
Open http://localhost:5000

## Run with plain docker commands
    docker network create dataentry-net
    docker run -d --name dataentry-mongo --network dataentry-net -v mongo_data:/data/db mongo:7
    docker build -t dataentry-app:1.0 .
    docker run -d --name dataentry-web --network dataentry-net -p 5000:5000 \
      -e MONGO_URI=mongodb://dataentry-mongo:27017 dataentry-app:1.0

## Useful
- API: http://localhost:5000/api/records
- Health: http://localhost:5000/health
- Logs: docker compose logs -f web
- Stop: docker compose down   (add -v to also delete data)
