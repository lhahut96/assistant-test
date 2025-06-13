## Features

- **Categories Scraping**: Extracts all support categories and their articles
- **Popular Articles**: Identifies and scrapes popular articles from the main page
- **Article Content**: Retrieves full article content, images, and internal links
- **Contact Information**: Extracts support contact details
- **Multiple Output Formats**: Saves data as JSON and CSV files
- **Respectful Scraping**: Includes delays between requests to avoid overwhelming the server

## Installation

### Method 1: Using Docker Compose (Recommended)

1. Clone the repository and navigate to the project directory
2. Copy the environment file and configure your API keys:
```bash
cp .env.example .env
```
3. Edit `.env` and add your OpenAI API key and vector store name
4. Build and run with Docker Compose:
```bash
docker-compose up -d
```

The scraper will run automatically based on the cron schedule (daily at 2:00 AM UTC). You can view logs with:
```bash
docker-compose logs -f scrape-bot
```

### Method 2: Manual Python Installation

1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

## Usage

### Docker Compose Usage (Automated)

Once running with Docker Compose, the scraper will automatically execute based on the cron schedule. You can:

- **View logs**: `docker-compose logs -f scrape-bot`
- **Check status**: `docker-compose ps`
- **Stop the service**: `docker-compose down`
- **Restart the service**: `docker-compose restart`
- **Access scraped articles**: Check the `./articles/` directory
- **View cron logs**: Check the `./logs/` directory

### Manual Execution

### Method 1: Run the batch script (Windows)
```bash
run_scraper.bat
```

### Method 2: Run directly with Python
```bash
python main.py
```

## Output Files

The scraper generates three output files:

1. **optisigns_data.json** - Complete scraped data in JSON format
2. **optisigns_articles.csv** - All articles data in CSV format
3. **optisigns_categories.csv** - Categories summary in CSV format

## Scraped Data Structure

### Categories
- Category name
- Category URL
- List of articles in each category

### Articles
- Article title
- Article URL
- Full text content
- Associated images
- Internal links
- Category classification

### Contact Information
- Support email addresses
- Phone numbers
- Support hours and additional details

## Customization

You can modify the scraper by:

1. **Changing the base URL**: Update the `base_url` parameter in the `OptiSignsScraper` class
2. **Adding more data fields**: Extend the `scrape_article_content` method
3. **Filtering content**: Add conditions in the scraping methods
4. **Adjusting delays**: Modify the `time.sleep()` values for different scraping speeds

## Example Usage

```python
from main import OptiSignsScraper

# Create scraper instance
scraper = OptiSignsScraper()

# Scrape the main page
scraper.scrape_main_page()

# Save data
scraper.save_data()

# Print summary
scraper.print_summary()
```

## Requirements

- Python 3.6+
- requests
- beautifulsoup4
- lxml
- pandas

## Notes

- The scraper is designed to be respectful to the website with built-in delays
- Large websites may take several minutes to scrape completely
- Network connectivity is required for scraping
- Some content may require different parsing depending on website updates

## Legal Notice

Please ensure you comply with the website's terms of service and robots.txt before scraping. This tool is for educational and legitimate research purposes.
