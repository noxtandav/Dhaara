module.exports = {
  apps: [
    {
      name: "dhaara",
      script: "./venv/bin/python",
      cwd: "/Users/shri/Documents/PAI/Dhaara",
      args: ["-m", "src.main"],
      env: {
        PYTHONPATH: "${PYTHONPATH}:/Users/shri/Documents/PAI/Dhaara/src",
      },
      env_production: {
        NODE_ENV: "production"
      },
    },
  ],
};

// Or just define as app in JSON format
// Ref 1: // Asynchronously load the Jobs Data? 