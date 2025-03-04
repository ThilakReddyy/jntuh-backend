# JNTUH Results API 

[![License](https://img.shields.io/github/license/thilakreddyy/jntuhresults-web.svg)](https://github.com/ThilakReddyy/jntuh-backend/blob/main/LICENSE)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/thilakreddyy/jntuh-backend.svg)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fjntuhresults.dhethi.com/docs&Website-Jntuh%20Results-blue?style=flat&logo=world&logoColor=white)](https://jntuhresults.dhethi.com/docs)


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



