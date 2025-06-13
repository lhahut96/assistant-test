## Features

- **Categories Scraping**: Extracts all support categories and their articles
- **Popular Articles**: Identifies and scrapes popular articles from the main page
- **Article Content**: Retrieves full article content, images, and internal links
- **Contact Information**: Extracts support contact details
- **Multiple Output Formats**: Saves data as JSON and CSV files
- **Respectful Scraping**: Includes delays between requests to avoid overwhelming the server

## Installation

1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

## Usage

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
