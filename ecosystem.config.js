module.exports = {
  apps: [
    {
      name: "job-agent-backend",
      script: ".venv/Scripts/python.exe",
      args: "-m uvicorn backend.app.main:app --port 8000 --host 0.0.0.0",
      cwd: "./",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
      },
      env_production: {
        NODE_ENV: "production",
      }
    },
    {
      name: "job-agent-frontend",
      script: "npm",
      args: "run dev",
      cwd: "./frontend",
      instances: 1,
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development"
      }
    }
  ]
};
