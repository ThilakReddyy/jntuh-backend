# JNTUH Results BACKEND 

[![License](https://img.shields.io/github/license/thilakreddyy/jntuhresults-web.svg)](https://github.com/ThilakReddyy/jntuh-backend/blob/main/LICENSE)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/thilakreddyy/jntuh-backend.svg)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fjntuhresults.dhethi.com%2Fconnect&Website-Jntuh%20Results-blue?style=flat&logo=world&logoColor=white)](https://jntuhresults.dhethi.com/connect)


This FastAPI-based service provides access to **student results, academic records, and backlog details**. It integrates with **PostgreSQL**, **Redis**, and **RabbitMQ** for efficient data handling and messaging.

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Postgres](https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/Rabbitmq-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare-F38020?style=for-the-badge&logo=Cloudflare&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=for-the-badge&logo=Prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/grafana-%23F46800.svg?style=for-the-badge&logo=grafana&logoColor=white)
[![MCP](https://img.shields.io/badge/Model_Context_Protocol-000000?style=for-the-badge&logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/)




##  Features  

✅ **Fetch all results** for a student  
✅ **Retrieve academic records** based on student ID  
✅ **Check backlogs** (pending subjects)  
✅ **Uses Redis caching** for optimized performance  
✅ **RabbitMQ integration** for event-driven messaging  
✅ **Read-only MCP server** for AI assistants and compatible clients\
✅ **Docker support** for easy deployment  


## Tech Stack  

- **Backend**: FastAPI (Python)  
- **Database**: PostgreSQL  
- **Caching**: Redis  
- **Messaging Queue**: RabbitMQ  
- **Containerization**: Docker
- **Monitoring**: Prometheus, Grafana
- **AI Integration**: Model Context Protocol (MCP)

## 🔄 Result Read Path

Result requests use a cache-first, asynchronous-refresh flow:

```mermaid
flowchart TD
    request[Client requests a result view] --> api[FastAPI validates the roll number]
    api --> cache{View cached in Redis?}

    cache -->|Yes| cached[Return cached result - 200]
    cache -->|No| database{Student marks in PostgreSQL?}

    database -->|Yes| derive[Build the requested result view]
    derive --> cacheView[Cache the derived view]
    cacheView --> stored[Return stored result - 200]
    derive -. academic-result freshness refresh .-> queue[(RabbitMQ)]

    database -->|No| queue
    queue --> accepted[Return queued status - 202]
    queue --> worker[Result worker]
    worker --> jntuh[JNTUH result servers]
    jntuh --> normalize[Parse and normalize exam attempts]
    normalize --> persist[Upsert results in PostgreSQL]
    persist --> invalidate[Invalidate student result caches]
    persist --> notify[Send result-ready notification]
    invalidate --> retry[Client retries the result request]
    retry --> api
```

See [architecture.md](architecture.md) for the architecture diagrams, detailed result lifecycle, queue limits, data model, supporting subsystems, observability, and deployment topology.


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

## MCP Tools

The application exposes a read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server at:

```text
https://jntuhresults.dhethi.com/mcp
```

Open `/connect` for setup instructions, or add the server to an MCP-compatible client:

```json
{
  "mcpServers": {
    "jntuh-results": {
      "url": "https://jntuhresults.dhethi.com/mcp"
    }
  }
}
```

Available tools:

| Tool | Description |
| --- | --- |
| `get_all_result` | Retrieve every exam attempt for a student. |
| `get_academic_result` | Retrieve the consolidated best-attempt academic record. |
| `get_backlogs` | Retrieve pending subjects grouped by semester. |
| `get_credits_checker` | Compare earned and required credits for each academic year. |
| `get_result_contrast` | Compare the results of two students. |
| `check_grace_marks_eligibility` | Check whether grace marks can clear eligible backlogs. |
| `get_class_results` | Retrieve results for an entire class section. |
| `get_notifications` | Retrieve result notifications using filters. |
| `get_latest_notifications` | Retrieve the latest result notifications. |

Only these query operations are exposed; destructive and administrative endpoints are not available through MCP.

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
