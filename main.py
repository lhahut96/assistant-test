import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import html2text
import requests
from bs4 import BeautifulSoup


class Scraper:
    """A web scraper for OptSigns support articles"""
    
    def __init__(self, output_dir="articles"):
        """Initialize the scraper with default output directory"""
        self.output_dir = output_dir
        self.base_url = "https://support.optisigns.com/api/v2/help_center/en-us"
    
    def get_sections_from_category(self, category_id):
        """Get all sections from a specific category ID"""
        url = f"{self.base_url}/categories/{category_id}/sections?sort_by=position&sort_order=desc&per_page=100"

        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes

            data = response.json()
            sections = data.get("sections", [])

            section_ids = []
            for section in sections:
                section_id = section.get("id")
                section_name = section.get("name", "Unknown")
                if section_id:
                    section_ids.append(
                        {"id": section_id, "name": section_name, "category_id": category_id}
                    )

            return section_ids

        except requests.exceptions.RequestException as e:
            print(f"Error fetching sections for category {category_id}: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for category {category_id}: {e}")
            return []


    def create_slug(self, title):
        """Create a URL-friendly slug from article title"""
        # Convert to lowercase and replace spaces with hyphens
        slug = title.lower()
        # Remove special characters and keep only alphanumeric, spaces, and hyphens
        slug = re.sub(r'[^a-z0-9\s\-]', '', slug)
        # Replace multiple spaces or hyphens with single hyphen
        slug = re.sub(r'[\s\-]+', '-', slug)
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        return slug


    def html_to_markdown(self, html_content):
        """Convert HTML content to clean Markdown"""
        if not html_content:
            return ""
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements (nav, ads, scripts, etc.)
        for element in soup.find_all(['nav', 'script', 'style', 'aside', 'footer']):
            element.decompose()
        
        # Remove elements with common ad/navigation classes
        for element in soup.find_all(class_=re.compile(r'(nav|ad|advertisement|sidebar|footer|header)', re.I)):
            element.decompose()
        
        # Convert to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines
        h.unicode_snob = True
        h.mark_code = True
        
        markdown_content = h.handle(str(soup))
        
        # Clean up extra whitespace
        markdown_content = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown_content)
        markdown_content = markdown_content.strip()
        
        return markdown_content


    def save_article_as_markdown(self, article, output_dir=None):
        """Save article as Markdown file"""
        if output_dir is None:
            output_dir = self.output_dir
            
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create slug from title
        slug = self.create_slug(article['title'])
        filename = f"{slug}.md"
        filepath = os.path.join(output_dir, filename)
        
        # Convert HTML body to Markdown
        markdown_content = self.html_to_markdown(article.get('body', ''))
        
        # Create full markdown content with metadata
        full_content = f"""# {article['title']}

**Article ID:** {article['id']}  
**Section ID:** {article['section_id']}  
**URL:** {article.get('html_url', 'N/A')}  

---

{markdown_content}
"""
        
        # Save to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_content)
            return filepath
        except Exception as e:
            print(f"Error saving {filename}: {e}")
            return None


    def get_articles_from_section(self, section_id):
        """Get all articles from a specific section ID with full content"""
        url = f"{self.base_url}/sections/{section_id}/articles?sort_by=position&sort_order=desc&per_page=100"

        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes

            data = response.json()
            articles = data.get("articles", [])

            article_data = []
            for article in articles:
                article_id = article.get("id")
                article_title = article.get("title", "Unknown")
                article_body = article.get("body", "")
                article_html_url = article.get("html_url", "")
                if article_id:
                    article_data.append({
                        "id": article_id, 
                        "title": article_title, 
                        "body": article_body,
                        "html_url": article_html_url,
                        "section_id": section_id
                    })

            return article_data

        except requests.exceptions.RequestException as e:
            print(f"Error fetching articles for section {section_id}: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON for section {section_id}: {e}")
            return []


    def get_sections_from_categories_concurrent(self, category_ids):
        """Get all sections from multiple category IDs concurrently"""
        all_sections = []
        results = {}
        
        print("Fetching sections from all categories concurrently...")
        print("-" * 50)
        
        # Use ThreadPoolExecutor to fetch all categories concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all category requests
            future_to_category = {
                executor.submit(self.get_sections_from_category, category_id): category_id 
                for category_id in category_ids
            }
            
            # Process completed requests as they finish
            for future in as_completed(future_to_category):
                category_id = future_to_category[future]
                try:
                    sections = future.result()
                    results[category_id] = sections
                    print(f"✓ Category {category_id}: Found {len(sections)} sections")
                except Exception as exc:
                    print(f"✗ Category {category_id}: Error occurred - {exc}")
                    results[category_id] = []
        
        # Collect all sections in order of category IDs
        for category_id in category_ids:
            if category_id in results:
                sections = results[category_id]
                if sections:
                    print(f"\nCategory {category_id} sections:")
                    for section in sections:
                        print(f"  - Section ID: {section['id']}, Name: {section['name']}")
                    all_sections.extend(sections)
        
        return all_sections


    def get_articles_from_sections_concurrent(self, sections):
        """Get all articles from multiple section IDs concurrently and save as Markdown"""
        all_articles = []
        results = {}
        
        print("\nFetching articles from all sections concurrently...")
        print("-" * 50)
        
        # Use ThreadPoolExecutor to fetch all sections concurrently
        with ThreadPoolExecutor(max_workers=15) as executor:
            # Submit all section requests
            future_to_section = {
                executor.submit(self.get_articles_from_section, section['id']): section 
                for section in sections
            }
            
            # Process completed requests as they finish
            for future in as_completed(future_to_section):
                section = future_to_section[future]
                section_id = section['id']
                section_name = section['name']
                try:
                    articles = future.result()
                    results[section_id] = articles
                    print(f"✓ Section {section_name} ({section_id}): Found {len(articles)} articles")
                except Exception as exc:
                    print(f"✗ Section {section_name} ({section_id}): Error occurred - {exc}")
                    results[section_id] = []
        
        # Collect all articles in order of sections and save as Markdown
        print("\nSaving articles as Markdown files...")
        print("-" * 50)
        
        saved_count = 0
        for section in sections:
            section_id = section['id']
            if section_id in results:
                articles = results[section_id]
                for article in articles:
                    filepath = self.save_article_as_markdown(article)
                    if filepath:
                        saved_count += 1
                        print(f"✓ Saved: {os.path.basename(filepath)}")
                    else:
                        print(f"✗ Failed to save: {article['title']}")
                all_articles.extend(articles)
        
        print(f"\nSuccessfully saved {saved_count} articles as Markdown files")
        return all_articles


    def run(self, category_ids):
        """Run the complete scraping process"""
        # Get all sections from categories concurrently
        all_sections = self.get_sections_from_categories_concurrent(category_ids)
        
        print("-" * 50)
        print(f"Total sections found: {len(all_sections)}")

        # Get all articles from sections concurrently
        all_articles = self.get_articles_from_sections_concurrent(all_sections)

        print("-" * 50)
        print(f"Total articles found: {len(all_articles)}")

        # Extract just the section IDs and article IDs
        section_ids_only = [section["id"] for section in all_sections]
        article_ids_only = [article["id"] for article in all_articles]

        print(f"Section IDs: {section_ids_only}")
        print(f"Article IDs: {article_ids_only}")
        
        return all_sections, all_articles


def main():
    CATEGORY_IDS = [
        360001365953,
        26318380891923,
        26318446072467,
        26318443842835,
        26318489475347,
        26318481473811,
        26318513597459,
        26318520668307,
        26318549123731,
        26318533891219,
        26318541299475,
        26318562916755,
    ]

    # Create scraper instance and run
    scraper = Scraper()
    scraper.run(CATEGORY_IDS)


if __name__ == "__main__":
    main()
