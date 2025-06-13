import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import client
from pathlib import Path

import html2text
import httpx
import openai
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI


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
                        {
                            "id": section_id,
                            "name": section_name,
                            "category_id": category_id,
                        }
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
        slug = re.sub(r"[^a-z0-9\s\-]", "", slug)
        # Replace multiple spaces or hyphens with single hyphen
        slug = re.sub(r"[\s\-]+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def html_to_markdown(self, html_content):
        """Convert HTML content to clean Markdown"""
        if not html_content:
            return ""

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted elements (nav, ads, scripts, etc.)
        for element in soup.find_all(["nav", "script", "style", "aside", "footer"]):
            element.decompose()

        # Remove elements with common ad/navigation classes
        for element in soup.find_all(
            class_=re.compile(r"(nav|ad|advertisement|sidebar|footer|header)", re.I)
        ):
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
        markdown_content = re.sub(r"\n\s*\n\s*\n", "\n\n", markdown_content)
        markdown_content = markdown_content.strip()

        return markdown_content

    def load_articles_metadata(self, output_dir=None):
        """Load articles metadata from the central JSON file"""
        if output_dir is None:
            output_dir = self.output_dir

        metadata_file = os.path.join(output_dir, "articles_metadata.json")

        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading metadata file: {e}")
                return {}
        return {}

    def save_articles_metadata(self, metadata_dict, output_dir=None):
        """Save articles metadata to the central JSON file"""
        if output_dir is None:
            output_dir = self.output_dir

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        metadata_file = os.path.join(output_dir, "articles_metadata.json")

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata file: {e}")

    def save_article_as_markdown(self, article, output_dir=None):
        """Save article as Markdown file using article ID as filename and update central metadata"""
        if output_dir is None:
            output_dir = self.output_dir

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Load existing metadata
        all_metadata = self.load_articles_metadata(output_dir)

        # Use article ID as filename instead of title slug
        article_id = str(article["id"])
        filename = f"{article_id}.md"
        filepath = os.path.join(output_dir, filename)

        # Check if article needs updating by comparing edited_at dates
        should_update = True
        existing_article = all_metadata.get(article_id, {})
        existing_edited_at = existing_article.get("edited_at")
        current_edited_at = article.get("edited_at")

        if existing_edited_at == current_edited_at:
            should_update = False
            print(
                f"⏭ Skipping {filename} - no changes detected (edited_at: {current_edited_at})"
            )
        else:
            if existing_edited_at:
                print(
                    f"🔄 Updating {filename} - changes detected (old: {existing_edited_at}, new: {current_edited_at})"
                )
            else:
                print(f"📄 Creating new {filename} (edited_at: {current_edited_at})")

        if not should_update:
            return filepath

        # Convert HTML body to Markdown
        markdown_content = self.html_to_markdown(article.get("body", ""))

        # Create full markdown content with metadata
        full_content = f"""# {article['title']}

**Article ID:** {article['id']}  
**Section ID:** {article['section_id']}  
**URL:** {article.get('html_url', 'N/A')}  
**Created At:** {article.get('created_at', 'N/A')}  
**Updated At:** {article.get('updated_at', 'N/A')}  
**Edited At:** {article.get('edited_at', 'N/A')}  

---

{markdown_content}
"""

        # Save markdown file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_content)

            # Update metadata in the central store
            all_metadata[article_id] = {
                "id": article["id"],
                "title": article["title"],
                "section_id": article["section_id"],
                "html_url": article.get("html_url"),
                "created_at": article.get("created_at"),
                "updated_at": article.get("updated_at"),
                "edited_at": article.get("edited_at"),
                "markdown_file": filename,
                "last_scraped": self.get_current_timestamp(),
                "openai_upload_status": "pending",  # Track upload status
            }

            # Save updated metadata
            self.save_articles_metadata(all_metadata, output_dir)

            return filepath
        except Exception as e:
            print(f"Error saving {filename}: {e}")
            return None

    def get_current_timestamp(self):
        """Get current timestamp in ISO format"""
        from datetime import datetime

        return datetime.now().isoformat()

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
                article_edited_at = article.get("edited_at")
                article_created_at = article.get("created_at")
                article_updated_at = article.get("updated_at")
                if article_id:
                    article_data.append(
                        {
                            "id": article_id,
                            "title": article_title,
                            "body": article_body,
                            "html_url": article_html_url,
                            "section_id": section_id,
                            "edited_at": article_edited_at,
                            "created_at": article_created_at,
                            "updated_at": article_updated_at,
                        }
                    )

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
                executor.submit(
                    self.get_sections_from_category, category_id
                ): category_id
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
                        print(
                            f"  - Section ID: {section['id']}, Name: {section['name']}"
                        )
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
                executor.submit(self.get_articles_from_section, section["id"]): section
                for section in sections
            }

            # Process completed requests as they finish
            for future in as_completed(future_to_section):
                section = future_to_section[future]
                section_id = section["id"]
                section_name = section["name"]
                try:
                    articles = future.result()
                    results[section_id] = articles
                    print(
                        f"✓ Section {section_name} ({section_id}): Found {len(articles)} articles"
                    )
                except Exception as exc:
                    print(
                        f"✗ Section {section_name} ({section_id}): Error occurred - {exc}"
                    )
                    results[section_id] = []

        # Collect all articles in order of sections and save as Markdown
        print("\nSaving articles as Markdown files...")
        print("-" * 50)

        saved_count = 0
        for section in sections:
            section_id = section["id"]
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

    def load_articles_metadata(self, articles_directory="articles"):
        """Load articles metadata from the central JSON file"""
        metadata_file = os.path.join(articles_directory, "articles_metadata.json")

        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading metadata file: {e}")
                return {}
        return {}

    def save_articles_metadata(self, metadata_dict, articles_directory="articles"):
        """Save articles metadata to the central JSON file"""
        if not os.path.exists(articles_directory):
            os.makedirs(articles_directory)

        metadata_file = os.path.join(articles_directory, "articles_metadata.json")

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata file: {e}")

    def update_upload_status(
        self,
        article_id,
        status,
        openai_file_id=None,
        error=None,
        articles_directory="articles",
    ):
        """Update the upload status of an article in the metadata"""
        metadata = self.load_articles_metadata(articles_directory)

        if str(article_id) in metadata:
            from datetime import datetime

            metadata[str(article_id)]["openai_upload_status"] = status
            metadata[str(article_id)][
                "last_upload_attempt"
            ] = datetime.now().isoformat()

            if openai_file_id:
                metadata[str(article_id)]["openai_file_id"] = openai_file_id

            if error:
                metadata[str(article_id)]["upload_error"] = error
            elif "upload_error" in metadata[str(article_id)]:
                # Clear previous errors on successful upload
                del metadata[str(article_id)]["upload_error"]

            self.save_articles_metadata(metadata, articles_directory)

    def get_articles_for_upload(
        self, articles_directory="articles", force_reupload=False
    ):
        """Get list of articles that need to be uploaded to OpenAI"""
        metadata = self.load_articles_metadata(articles_directory)
        articles_to_upload = []

        for article_id, article_data in metadata.items():
            upload_status = article_data.get("openai_upload_status", "pending")
            current_updated_at = article_data.get("updated_at")
            last_uploaded_version = article_data.get("last_uploaded_updated_at")

            should_upload = False
            reason = ""

            if force_reupload:
                should_upload = True
                reason = "force_reupload"
            elif upload_status == "pending":
                should_upload = True
                reason = "never_uploaded"
            elif upload_status == "failed":
                should_upload = True
                reason = "previous_upload_failed"
            elif upload_status == "uploaded":
                # Check if content has been updated since last upload
                if current_updated_at and last_uploaded_version:
                    if current_updated_at != last_uploaded_version:
                        should_upload = True
                        reason = "content_updated"
                elif current_updated_at and not last_uploaded_version:
                    # Old metadata format, assume needs update
                    should_upload = True
                    reason = "metadata_migration"

            if should_upload:
                md_file = os.path.join(articles_directory, f"{article_id}.md")
                if os.path.exists(md_file):
                    articles_to_upload.append(
                        {
                            "article_id": article_id,
                            "file_path": md_file,
                            "title": article_data.get("title", "Unknown"),
                            "edited_at": article_data.get("edited_at"),
                            "updated_at": current_updated_at,
                            "last_uploaded_version": last_uploaded_version,
                            "current_status": upload_status,
                            "upload_reason": reason,
                        }
                    )

        return articles_to_upload

    def get_article_metadata(self, articles_directory="articles", article_id=None):
        """Get metadata for articles, optionally for a specific article ID"""
        metadata = self.load_articles_metadata(articles_directory)

        if article_id:
            return metadata.get(str(article_id))
        else:
            return metadata

    def upload_article_by_id(
        self,
        article_id,
        articles_directory="articles",
        purpose="assistants",
        force_reupload=False,
    ):
        """Upload a specific article by its ID"""
        directory_path = Path(articles_directory)

        if not directory_path.exists():
            print(f"Directory {articles_directory} does not exist.")
            return None

        # Get metadata
        metadata = self.get_article_metadata(articles_directory, article_id)
        if not metadata:
            print(f"No metadata found for article ID {article_id}")
            return None

        # Check if upload is needed based on content updates
        current_status = metadata.get("openai_upload_status", "pending")
        current_updated_at = metadata.get("updated_at")
        last_uploaded_version = metadata.get("last_uploaded_updated_at")

        if current_status == "uploaded" and not force_reupload:
            # Check if content has been updated since last upload
            if (
                current_updated_at
                and last_uploaded_version
                and current_updated_at == last_uploaded_version
            ):
                print(
                    f"Article {article_id} is up to date (File ID: {metadata.get('openai_file_id')})"
                )
                print(f"Last uploaded version: {last_uploaded_version}")
                print("Content has not changed since last upload")
                return {
                    "article_id": article_id,
                    "status": "skipped",
                    "reason": "up_to_date",
                    "openai_file_id": metadata.get("openai_file_id"),
                }
            elif (
                current_updated_at
                and last_uploaded_version
                and current_updated_at != last_uploaded_version
            ):
                print(f"Article {article_id} has been updated since last upload")
                print(f"Last uploaded: {last_uploaded_version}")
                print(f"Current version: {current_updated_at}")
                print("Will re-upload with updated content...")
            elif not last_uploaded_version:
                print(
                    f"Article {article_id} missing upload version info, will re-upload to be safe..."
                )

        # Look for the specific markdown file
        md_file = directory_path / f"{article_id}.md"

        if not md_file.exists():
            print(f"Article {article_id}.md not found in {articles_directory}")
            return None

        print(f"Attempting to upload article ID: {article_id}")
        print(f"Title: {metadata.get('title', 'Unknown')}")
        print(f"Last edited: {metadata.get('edited_at', 'Unknown')}")
        print(f"Current status: {current_status}")
        print("-" * 50)

        try:
            with open(md_file, "rb") as f:
                response = self.client.files.create(
                    file=f,
                    purpose=purpose,
                )

            # Update metadata with success
            self.update_upload_status(
                article_id,
                "uploaded",
                response.id,
                articles_directory=articles_directory,
            )

            upload_result = {
                "local_path": str(md_file),
                "file_name": md_file.name,
                "article_id": article_id,
                "openai_file_id": response.id,
                "status": "success",
                "metadata": metadata,
            }

            print(f"✓ Successfully uploaded {md_file.name}")
            print(f"  File ID: {response.id}")
            print(f"  Article ID: {article_id}")
            print(f"  Title: {metadata.get('title')}")

            return upload_result

        except Exception as e:
            # Update metadata with failure
            self.update_upload_status(
                article_id,
                "failed",
                error=str(e),
                articles_directory=articles_directory,
            )

            error_result = {
                "local_path": str(md_file),
                "file_name": md_file.name,
                "article_id": article_id,
                "error": str(e),
                "status": "failed",
                "metadata": metadata,
            }

            print(f"✗ Failed to upload {md_file.name}: {e}")
            return error_result

    def upload_pending_articles(
        self, articles_directory="articles", purpose="assistants", max_uploads=None
    ):
        """Upload all articles that are pending or failed upload using batch upload"""
        articles_to_upload = self.get_articles_for_upload(
            articles_directory, force_reupload=False
        )

        if not articles_to_upload:
            print("No articles pending upload.")
            return []

        if max_uploads:
            articles_to_upload = articles_to_upload[:max_uploads]

        print(f"Found {len(articles_to_upload)} articles to upload:")
        for article in articles_to_upload:
            reason = article.get("upload_reason", "unknown")
            status = article["current_status"]
            print(
                f"  - {article['article_id']}: {article['title']} (status: {status}, reason: {reason})"
            )
            if reason == "content_updated":
                print(
                    f"    Updated: {article.get('last_uploaded_version')} → {article.get('updated_at')}"
                )

        # Collect file paths for batch upload
        file_paths = [article["file_path"] for article in articles_to_upload]

        print(f"\nStarting batch upload of {len(file_paths)} files...")
        print("-" * 50)

        # Use batch upload method
        uploaded_files, failed_uploads = self.upload_files_batch(
            file_paths, purpose, articles_directory
        )

        # Combine results
        results = uploaded_files + failed_uploads

        # Summary
        successful = len(uploaded_files)
        failed = len(failed_uploads)

        print("\n" + "-" * 50)
        print("BATCH UPLOAD SUMMARY")
        print("-" * 50)
        print(f"Total processed: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")

        return results

    # ...existing code...


class OpenAIUploader:
    """A utility class for uploading markdown files to OpenAI in batches"""

    def __init__(self, api_key=None):
        """Initialize the uploader with OpenAI client"""
        print(os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.store = None
        print("OpenAI client initialized.")

    def get_markdown_file_paths(self, directory):
        """Get all markdown file paths from a directory"""
        md_files = []
        directory_path = Path(directory)

        if not directory_path.exists():
            print(f"Directory {directory} does not exist.")
            return md_files

        # Collect all .md files
        for file_path in directory_path.glob("*.md"):
            md_files.append(str(file_path))

        print(f"Found {len(md_files)} markdown files in {directory}")
        return md_files

    def upload_files_batch(
        self, file_paths, purpose="assistants", articles_directory="articles"
    ):
        """Upload multiple files to OpenAI using the files.create API and update metadata"""
        uploaded_files = []
        failed_uploads = []

        print("\nStarting batch upload to OpenAI...")
        print("-" * 50)

        for file_path in file_paths:
            try:
                file_name = os.path.basename(file_path)
                # Extract article ID from filename (assuming format: {article_id}.md)
                article_id = os.path.splitext(file_name)[0]

                print(f"Uploading {file_name}...")

                with open(file_path, "rb") as f:
                    response = self.client.files.create(
                        file=f,
                        purpose=purpose,
                    )

                # Update metadata with successful upload
                self.update_upload_status(
                    article_id,
                    "uploaded",
                    response.id,
                    articles_directory=articles_directory,
                )

                uploaded_files.append(
                    {
                        "local_path": file_path,
                        "file_name": file_name,
                        "article_id": article_id,
                        "openai_file_id": response.id,
                        "status": "success",
                    }
                )

                print(f"✓ Successfully uploaded {file_name} - File ID: {response.id}")

            except Exception as e:
                # Extract article ID for failed uploads too
                file_name = os.path.basename(file_path)
                article_id = os.path.splitext(file_name)[0]

                # Update metadata with failed upload
                self.update_upload_status(
                    article_id,
                    "failed",
                    error=str(e),
                    articles_directory=articles_directory,
                )

                failed_uploads.append(
                    {
                        "local_path": file_path,
                        "file_name": file_name,
                        "article_id": article_id,
                        "error": str(e),
                        "status": "failed",
                    }
                )
                print(f"✗ Failed to upload {file_name}: {e}")

        # Print summary
        print("\n" + "-" * 50)
        print("UPLOAD SUMMARY")
        print("-" * 50)
        print(f"Total files processed: {len(file_paths)}")
        print(f"Successfully uploaded: {len(uploaded_files)}")
        print(f"Failed uploads: {len(failed_uploads)}")

        if uploaded_files:
            print("\nSuccessfully uploaded files:")
            for file_info in uploaded_files:
                print(f"  ✓ {file_info['file_name']} -> {file_info['openai_file_id']}")

        if failed_uploads:
            print("\nFailed uploads:")
            for file_info in failed_uploads:
                print(f"  ✗ {file_info['file_name']}: {file_info['error']}")

        return uploaded_files, failed_uploads

    def upload_markdown_files_batch(self, directory, purpose="assistants"):
        """Main method to upload markdown files from a directory that need uploading"""
        # Get all markdown file paths
        all_file_paths = self.get_markdown_file_paths(directory)

        if not all_file_paths:
            print("No markdown files found to upload.")
            return [], []

        # Load metadata to check upload status
        metadata = self.load_articles_metadata(directory)
        files_to_upload = []

        print("Checking upload status for all markdown files...")
        print("-" * 50)

        for file_path in all_file_paths:
            file_name = os.path.basename(file_path)
            article_id = os.path.splitext(file_name)[0]

            article_data = metadata.get(article_id, {})
            upload_status = article_data.get("openai_upload_status", "pending")
            current_updated_at = article_data.get("updated_at")
            last_uploaded_version = article_data.get("last_uploaded_updated_at")

            should_upload = False
            reason = ""

            if upload_status == "pending":
                should_upload = True
                reason = "never_uploaded"
            elif upload_status == "failed":
                should_upload = True
                reason = "previous_upload_failed"
            elif upload_status == "uploaded":
                # Check if content has been updated since last upload
                if current_updated_at and last_uploaded_version:
                    if current_updated_at != last_uploaded_version:
                        should_upload = True
                        reason = "content_updated"
                elif current_updated_at and not last_uploaded_version:
                    # Old metadata format, assume needs update
                    should_upload = True
                    reason = "metadata_migration"

            if should_upload:
                files_to_upload.append(file_path)
                title = article_data.get("title", "Unknown")
                print(f"  📤 {article_id}: {title} (reason: {reason})")
            else:
                print(
                    f"  ⏭ {article_id}: Up to date (File ID: {article_data.get('openai_file_id', 'N/A')})"
                )

        if not files_to_upload:
            print("\nAll files are up to date - no uploads needed.")
            return [], []

        print(
            f"\nFound {len(files_to_upload)} files that need uploading out of {len(all_file_paths)} total files."
        )

        # Upload only files that need uploading
        return self.upload_files_batch(
            files_to_upload, purpose, articles_directory=directory
        )

    def upload_single_file_from_articles(
        self, articles_directory="articles", purpose="assistants"
    ):
        """Upload a single file from the articles folder (first pending article)"""
        articles_to_upload = self.get_articles_for_upload(
            articles_directory, force_reupload=False
        )

        if not articles_to_upload:
            print("No articles pending upload.")
            return None

        # Select the first pending article
        selected_article = articles_to_upload[0]
        article_id = selected_article["article_id"]

        print(f"Selected article for upload:")
        print(f"  ID: {article_id}")
        print(f"  Title: {selected_article['title']}")
        print(f"  Status: {selected_article['current_status']}")
        print(f"  Last edited: {selected_article['edited_at']}")
        print()

        return self.upload_article_by_id(article_id, articles_directory, purpose)

    def get_uploaded_files_info(self, articles_directory="articles"):
        """Get information about files that have been uploaded to OpenAI"""
        metadata = self.load_articles_metadata(articles_directory)
        uploaded_files = []

        for article_id, article_data in metadata.items():
            if article_data.get(
                "openai_upload_status"
            ) == "uploaded" and article_data.get("openai_file_id"):
                uploaded_files.append(
                    {
                        "article_id": article_id,
                        "title": article_data.get("title", "Unknown"),
                        "openai_file_id": article_data.get("openai_file_id"),
                        "upload_date": article_data.get("last_upload_attempt"),
                        "edited_at": article_data.get("edited_at"),
                    }
                )

        return uploaded_files

    def update_upload_status(
        self,
        article_id,
        status,
        openai_file_id=None,
        error=None,
        articles_directory="articles",
    ):
        """Update the upload status of an article in the metadata"""
        metadata = self.load_articles_metadata(articles_directory)

        if str(article_id) in metadata:
            from datetime import datetime

            metadata[str(article_id)]["openai_upload_status"] = status
            metadata[str(article_id)][
                "last_upload_attempt"
            ] = datetime.now().isoformat()

            if openai_file_id:
                metadata[str(article_id)]["openai_file_id"] = openai_file_id
                # Save the current updated_at as the version that was uploaded
                current_updated_at = metadata[str(article_id)].get("updated_at")
                if current_updated_at:
                    metadata[str(article_id)][
                        "last_uploaded_updated_at"
                    ] = current_updated_at

            if error:
                metadata[str(article_id)]["upload_error"] = error
            elif "upload_error" in metadata[str(article_id)]:
                # Clear previous errors on successful upload
                del metadata[str(article_id)]["upload_error"]

            self.save_articles_metadata(metadata, articles_directory)

    def save_articles_metadata(self, metadata_dict, articles_directory="articles"):
        """Save articles metadata to the central JSON file"""
        if not os.path.exists(articles_directory):
            os.makedirs(articles_directory)

        metadata_file = os.path.join(articles_directory, "articles_metadata.json")

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata file: {e}")

    def load_articles_metadata(self, articles_directory="articles"):
        """Load articles metadata from the central JSON file"""
        metadata_file = os.path.join(articles_directory, "articles_metadata.json")

        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading metadata file: {e}")
                return {}
        return {}

    def upload_articles_by_ids_batch(
        self,
        article_ids,
        articles_directory="articles",
        purpose="assistants",
        force_reupload=False,
    ):
        """Upload multiple specific articles by their IDs using batch upload"""
        if not article_ids:
            print("No article IDs provided.")
            return []

        # Get metadata and filter for valid articles
        metadata = self.load_articles_metadata(articles_directory)
        valid_articles = []
        file_paths = []

        for article_id in article_ids:
            article_data = metadata.get(str(article_id))
            if not article_data:
                print(f"⚠ No metadata found for article ID {article_id}")
                continue

            md_file = os.path.join(articles_directory, f"{article_id}.md")
            if not os.path.exists(md_file):
                print(f"⚠ File not found: {article_id}.md")
                continue

            # Check if upload is needed (unless force_reupload)
            if not force_reupload:
                current_status = article_data.get("openai_upload_status", "pending")
                current_updated_at = article_data.get("updated_at")
                last_uploaded_version = article_data.get("last_uploaded_updated_at")

                if (
                    current_status == "uploaded"
                    and current_updated_at == last_uploaded_version
                ):
                    print(f"⏭ Skipping {article_id} - already up to date")
                    continue

            valid_articles.append(
                {
                    "article_id": article_id,
                    "title": article_data.get("title", "Unknown"),
                    "file_path": md_file,
                }
            )
            file_paths.append(md_file)

        if not file_paths:
            print("No articles need uploading.")
            return []

        print(f"Batch uploading {len(file_paths)} articles:")
        for article in valid_articles:
            print(f"  - {article['article_id']}: {article['title']}")

        print(f"\nStarting batch upload...")
        print("-" * 50)

        # Use batch upload method
        uploaded_files, failed_uploads = self.upload_files_batch(
            file_paths, purpose, articles_directory
        )

        # Combine results
        results = uploaded_files + failed_uploads

        print(
            f"\nBatch upload completed: {len(uploaded_files)} successful, {len(failed_uploads)} failed"
        )

        return results

    # ...existing code...
    def create_and_check_vector_store(self):
        """Create and check the vector store for articles"""
        print("Checking if vector store exists...")
        try:
            vector_store_name = os.getenv("VECTOR_STORE")
            if not vector_store_name:
                print("❌ VECTOR_STORE environment variable not set!")
                return None

            vector_stores = self.client.vector_stores.list()
            store = None

            # Check if vector store already exists
            for current_store in vector_stores.data:
                if current_store.name == vector_store_name:
                    print(
                        f"✓ Vector store '{vector_store_name}' already exists (ID: {current_store.id})"
                    )
                    store = current_store
                    break
            else:
                # Create new vector store if it doesn't exist
                print(f"Creating new vector store: '{vector_store_name}'...")
                store = self.client.vector_stores.create(
                    name=vector_store_name,
                    chunking_strategy={
                        "type": "static",
                        "static": {
                            "chunk_overlap_tokens": 400,
                            "max_chunk_size_tokens": 2048,
                        },
                    },
                )
                print(f"✓ Created new vector store: {store.name} (ID: {store.id})")

            self.store = store

            # Show vector store details
            print(f"Vector Store Details:")
            print(f"  Name: {store.name}")
            print(f"  ID: {store.id}")
            print(
                f"  File count: {store.file_counts.total if hasattr(store, 'file_counts') else 'Unknown'}"
            )

            return store

        except Exception as e:
            print(f"❌ Error with vector store: {e}")
            return None

    def attach_files_to_vector_store(self, file_id):
        """Attach a single file to the vector store"""
        if not self.store:
            print("No vector store available to attach files.")
            return False

        try:
            response = self.client.post(
                f"/vector_stores/{self.store.id}/files",
                body={"file_id": file_id},
                cast_to=httpx.Response,
            )
            print(f"✓ Successfully attached file {file_id} to vector store")
            return True

        except Exception as e:
            print(f"✗ Error attaching file {file_id} to vector store: {e}")
            return False

    def attach_uploaded_files_to_vector_store(self, articles_directory="articles"):
        """Read metadata and attach all uploaded files to the vector store"""
        if not self.store:
            print(
                "No vector store available. Call create_and_check_vector_store() first."
            )
            return

        # Load metadata to get uploaded file IDs
        metadata = self.load_articles_metadata(articles_directory)

        if not metadata:
            print("No metadata found.")
            return

        # Find all files that have been uploaded to OpenAI
        uploaded_files = []
        for article_id, article_data in metadata.items():
            if article_data.get(
                "openai_upload_status"
            ) == "uploaded" and article_data.get("openai_file_id"):
                uploaded_files.append(
                    {
                        "article_id": article_id,
                        "file_id": article_data["openai_file_id"],
                        "title": article_data.get("title", "Unknown"),
                    }
                )

        if not uploaded_files:
            print("No uploaded files found in metadata.")
            return

        print(f"Found {len(uploaded_files)} uploaded files to attach to vector store:")
        print("-" * 60)

        successful_attachments = 0
        failed_attachments = 0

        for file_info in uploaded_files:
            print(f"Attaching {file_info['article_id']}: {file_info['title']}")

            if self.attach_files_to_vector_store(file_info["file_id"]):
                successful_attachments += 1
            else:
                failed_attachments += 1

        print("-" * 60)
        print("VECTOR STORE ATTACHMENT SUMMARY")
        print("-" * 60)
        print(f"Total files processed: {len(uploaded_files)}")
        print(f"Successfully attached: {successful_attachments}")
        print(f"Failed attachments: {failed_attachments}")

        return {
            "total": len(uploaded_files),
            "successful": successful_attachments,
            "failed": failed_attachments,
        }


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

    # upload_single_article()
    # Upload files to OpenAI using batch uploader
    uploader = OpenAIUploader()
    uploader.upload_markdown_files_batch(scraper.output_dir)

    # Create vector store and attach uploaded files
    uploader.create_and_check_vector_store()
    uploader.attach_uploaded_files_to_vector_store()


def upload_single_article():
    """Convenience function to upload a single pending article from the articles folder"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Upload a single pending article
    result = uploader.upload_single_file_from_articles()

    if result and result.get("status") == "success":
        print(f"\nUpload completed successfully!")
        print(f"OpenAI File ID: {result['openai_file_id']}")
        print(f"Article ID: {result['article_id']}")
    elif result and result.get("status") == "skipped":
        print(f"\nUpload skipped: {result.get('reason')}")
    else:
        print(f"\nUpload failed!")
        if result:
            print(f"Error: {result.get('error', 'Unknown error')}")


def upload_all_pending_articles(max_uploads=None):
    """Convenience function to upload all pending articles"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Upload all pending articles
    results = uploader.upload_pending_articles(max_uploads=max_uploads)

    if results:
        successful = sum(1 for r in results if r.get("status") == "success")
        print(
            f"\nCompleted! Successfully uploaded {successful} out of {len(results)} articles."
        )
    else:
        print("\nNo articles were processed.")


def show_upload_status():
    """Show the upload status of all articles"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Get all metadata
    metadata = uploader.get_article_metadata()

    if not metadata:
        print("No articles found in metadata.")
        return

    # Count by status
    status_counts = {}
    for article_id, article_data in metadata.items():
        status = article_data.get("openai_upload_status", "pending")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("Article Upload Status Summary:")
    print("-" * 40)
    for status, count in status_counts.items():
        print(f"{status.title()}: {count}")

    print(f"\nTotal articles: {len(metadata)}")

    # Show pending/failed articles
    pending_articles = []
    for article_id, article_data in metadata.items():
        status = article_data.get("openai_upload_status", "pending")
        if status in ["pending", "failed"]:
            pending_articles.append(
                {
                    "id": article_id,
                    "title": article_data.get("title", "Unknown"),
                    "status": status,
                    "error": article_data.get("upload_error"),
                }
            )

    if pending_articles:
        print(f"\nArticles needing upload ({len(pending_articles)}):")
        print("-" * 40)
        for article in pending_articles[:10]:  # Show first 10
            print(f"  {article['id']}: {article['title']} ({article['status']})")
            if article["error"]:
                print(f"    Error: {article['error'][:100]}...")

        if len(pending_articles) > 10:
            print(f"  ... and {len(pending_articles) - 10} more")


def show_uploaded_files():
    """Show all files that have been uploaded to OpenAI with their file IDs"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Get uploaded files info
    uploaded_files = uploader.get_uploaded_files_info()

    if not uploaded_files:
        print("No files have been uploaded to OpenAI yet.")
        return

    print(f"Files uploaded to OpenAI ({len(uploaded_files)}):")
    print("-" * 80)
    print(f"{'Article ID':<15} {'OpenAI File ID':<30} {'Title':<30}")
    print("-" * 80)

    for file_info in uploaded_files:
        title = (
            file_info["title"][:27] + "..."
            if len(file_info["title"]) > 30
            else file_info["title"]
        )
        print(
            f"{file_info['article_id']:<15} {file_info['openai_file_id']:<30} {title:<30}"
        )

    print(f"\nTotal: {len(uploaded_files)} files uploaded")


# ...existing code...


def upload_articles_by_ids_batch_helper(article_ids, force_reupload=False):
    """Convenience function to batch upload specific articles by their IDs"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Upload the specific articles in batch
    results = uploader.upload_articles_by_ids_batch(
        article_ids, force_reupload=force_reupload
    )

    if results:
        successful = sum(1 for r in results if r.get("status") == "success")
        failed = sum(1 for r in results if r.get("status") == "failed")
        print(f"\nBatch upload completed!")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")

        if successful > 0:
            print("\nSuccessfully uploaded files:")
            for result in results:
                if result.get("status") == "success":
                    print(
                        f"  ✓ Article {result['article_id']}: {result['openai_file_id']}"
                    )
    else:
        print("\nNo articles were processed.")


def setup_vector_store_with_articles():
    """Convenience function to create vector store and attach all uploaded articles"""
    # Load environment variables
    load_dotenv()

    # Create uploader instance
    uploader = OpenAIUploader()

    # Create or check vector store
    store = uploader.create_and_check_vector_store()

    if not store:
        print("Failed to create or access vector store.")
        return None

    # Attach all uploaded files to the vector store
    print("\nAttaching uploaded files to vector store...")
    result = uploader.attach_uploaded_files_to_vector_store()

    if result:
        print(f"\n🎉 Vector store setup complete!")
        print(f"Vector Store ID: {store.id}")
        print(f"Files attached: {result['successful']}/{result['total']}")

    return result


def show_vector_store_info():
    """Show information about the current vector store"""
    load_dotenv()
    uploader = OpenAIUploader()

    vector_store_name = os.getenv("VECTOR_STORE")
    if not vector_store_name:
        print("❌ VECTOR_STORE environment variable not set!")
        return

    try:
        vector_stores = uploader.client.beta.vector_stores.list()

        for store in vector_stores.data:
            if store.name == vector_store_name:
                print(f"Vector Store: {store.name}")
                print(f"ID: {store.id}")
                print(f"Created: {store.created_at}")
                if hasattr(store, "file_counts"):
                    print(f"Total files: {store.file_counts.total}")
                    print(f"In progress: {store.file_counts.in_progress}")
                    print(f"Completed: {store.file_counts.completed}")
                    print(f"Failed: {store.file_counts.failed}")
                return

        print(f"Vector store '{vector_store_name}' not found.")

    except Exception as e:
        print(f"Error getting vector store info: {e}")


if __name__ == "__main__":
    load_dotenv()  # Load environment variables from .env file if needed
    main()
