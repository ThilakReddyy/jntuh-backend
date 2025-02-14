# JNTUH Results API 

This FastAPI-based service provides access to **student results, academic records, and backlog details**. It integrates with **PostgreSQL**, **Redis**, and **RabbitMQ** for efficient data handling and messaging.  

##  Features  

✅ **Fetch all results** for a student  
✅ **Retrieve academic records** based on student ID  
✅ **Check backlogs** (pending subjects)  
✅ **Uses Redis caching** for optimized performance  
✅ **RabbitMQ integration** for event-driven messaging  
✅ **Docker support** for easy deployment  


## Tech Stack  

- **Backend**: FastAPI (Python)  
- **Database**: PostgreSQL  
- **Caching**: Redis  
- **Messaging Queue**: RabbitMQ  
- **Containerization**: Docker  


## Installation & Setup  

### 1️⃣ Prerequisites  

Ensure you have **Docker** and **Docker Compose** installed.

### 2️⃣ Clone the Repository  

```bash
git clone https://github.com/ThilakReddyy/jntuh-backend
cd jntuh-backend
```

### 3️⃣ Start the Application

Run the API using Docker Compose:

```bash
docker-compose up --build
```
