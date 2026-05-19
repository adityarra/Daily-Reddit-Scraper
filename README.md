## Reddit Scraper
An automated, serverless pipeline that scrapes media (images and animated GIFs) from specified subreddits and streams them directly into a Discord channel using webhooks. 

The entire engine executes via GitHub Actions once a day, rotating target subreddits and upvote thresholds dynamically based on a custom timetable structure (config.json).

---

## Ecosystem Layout

```text
├── .github/workflows/
│   └── reddit_harvest.yml   
├── config.json              
├── scraper.py              
└── README.md               
```

---


##  Initial Setup
1. Configure the Weekly Timetable (config.json)
Modify the config.json file in your root workspace. Ensure each day contains an array of target subreddits and a clean integer score limit.

2. Register Environmental Access Keys (Secrets)
To connect the runner safely without hardcoding plain keys into public files, go to your GitHub Repository -> Settings -> Secrets and variables -> Actions -> New repository secret and add both `DISCORD_WEBHOOK_URL` and `SCRAPE_DO_TOKEN`.