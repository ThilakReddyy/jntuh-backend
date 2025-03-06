# JNTUH Results BACKEND 

[![License](https://img.shields.io/github/license/thilakreddyy/jntuhresults-web.svg)](https://github.com/ThilakReddyy/jntuh-backend/blob/main/LICENSE)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/thilakreddyy/jntuh-backend.svg)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fjntuhresults.dhethi.com/docs&Website-Jntuh%20Results-blue?style=flat&logo=world&logoColor=white)](https://jntuhresults.dhethi.com/docs)


This FastAPI-based service provides access to **student results, academic records, and backlog details**. It integrates with **PostgreSQL**, **Redis**, and **RabbitMQ** for efficient data handling and messaging.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Postgres](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/Rabbitmq-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?style=for-the-badge&logo=Cloudflare&logoColor=white)




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

## 🏗 System Architecture

   The following diagrams illustrate the components and overall architecture of the FastAPI-based results service.

### **Component Diagram**  
This diagram shows how different services interact in the system.  

![Component Diagram](https://github.com/ThilakReddyy/jntuh-backend/blob/main/assests/component-diagram.png)  

### **Architecture Diagram**  
This diagram outlines the flow of requests and data within the system.  

![Architecture Diagram](https://github.com/ThilakReddyy/jntuh-backend/blob/main/assests/architecture-diagram-horizontal.png)  


## Installation & Setup  

1. **Prerequisites:**

   Ensure you have **Docker** and **Docker Compose** installed.

2. **Clone the repository:**

   ```bash
   git clone https://github.com/thilakreddyy/jntuh-backend.git
   ```
   
3. **Navigate to the project directory:**

   ```bash
   cd jntuh-backend
   ```

4. **Build and start the Docker containers:**

   ```bash
   docker-compose up --build
   ```
   This command will build the Docker images and start the services defined in the docker-compose.yml file.

## Usage

Once the application is running, access the API documentation at http://localhost:8000/docs. This interactive documentation provides details about each endpoint and allows you to test them directly.

## Contributing

  Contributions are welcome! Please follow these steps:
  
1. Fork the repository.
2. Create a new branch (git checkout -b feature/YourFeature).
3. Commit your changes (git commit -m 'Add YourFeature').
4.  Push to the branch (git push origin feature/YourFeature).
5.  Open a Pull Request.

## License

This project is licensed under the GPL-3.0 .

## Acknowledgements

Special thanks to all contributors and the open-source community for their invaluable support.



