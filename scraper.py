import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import List, Dict, Set
import urllib.parse
import re
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class LinkedInJobScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        self.all_jobs = []
        
        # Improved location search terms that LinkedIn recognizes
        self.search_locations = {
            'UAE': [
                'Dubai, United Arab Emirates',
                'Abu Dhabi, United Arab Emirates', 
                'United Arab Emirates',
                'Dubai',
                'Abu Dhabi'
            ],
            'Saudi Arabia': [
                'Riyadh, Saudi Arabia',
                'Jeddah, Saudi Arabia',
                'Saudi Arabia',
                'Riyadh',
                'Jeddah'
            ],
            'Qatar': [
                'Doha, Qatar',
                'Qatar',
                'Doha'
            ],
            'United Kingdom': [
                'London, United Kingdom',
                'United Kingdom',
                'London',
                'Manchester, United Kingdom',
                'Birmingham, United Kingdom'
            ]
        }
        
        # Location validation patterns
        self.location_patterns = {
            'UAE': [
                r'\bdubai\b', r'\babu dhabi\b', r'\bsharjah\b', r'\bajman\b',
                r'\bunited arab emirates\b', r'\buae\b', r'\bemirati?\b'
            ],
            'Saudi Arabia': [
                r'\briyadh\b', r'\bjeddah\b', r'\bdammam\b', r'\bkhobar\b',
                r'\bsaudi arabia\b', r'\bksa\b', r'\bsaudi\b'
            ],
            'Qatar': [
                r'\bdoha\b', r'\bqatar\b', r'\bqatari?\b'
            ],
            'United Kingdom': [
                r'\blondon\b', r'\bmanchester\b', r'\bbirmingham\b', r'\bedinburgh\b',
                r'\bglasgow\b', r'\bunited kingdom\b', r'\bu\.?k\.?\b', r'\bbritain\b',
                r'\bengland\b', r'\bscotland\b', r'\bwales\b'
            ]
        }
        
        # Senior finance keywords for LinkedIn search
        self.finance_keywords = [
            "CFO",
            "Chief Financial Officer", 
            "Finance Director",
            "VP Finance",
            "SVP Finance",
            "Head of Finance",
            "Regional Finance Director",
            "Commercial Finance Director",
            "Treasury Director",
            "FP&A Director",
            "Financial Controller",
            "Group Finance Director"
        ]
        
    def load_companies_from_excel(self):
        """Load companies from Excel file"""
        try:
            df = pd.read_excel('top companies.xlsx', header=None, names=['company'])
            companies = df['company'].tolist()
            logging.info(f"Loaded {len(companies)} companies from Excel file")
            return companies
        except Exception as e:
            logging.error(f"Error loading companies from Excel: {e}")
            return []
    
    def load_seen_jobs(self):
        """Load previously seen jobs"""
        try:
            with open('seen_jobs.json', 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set()
    
    def save_seen_jobs(self, seen_jobs):
        """Save seen jobs to file"""
        with open('seen_jobs.json', 'w') as f:
            json.dump(list(seen_jobs), f, indent=2)
    
    def validate_job_location(self, job_text: str) -> str:
        """Validate job location using regex patterns"""
        job_text_lower = job_text.lower()
        
        for country, patterns in self.location_patterns.items():
            for pattern in patterns:
                if re.search(pattern, job_text_lower):
                    logging.debug(f"Location match: '{pattern}' found in job text for {country}")
                    return country
        
        return None
    
    def extract_detailed_location(self, job_text: str, validated_country: str) -> str:
        """Extract specific city/location after country validation"""
        job_text_lower = job_text.lower()
        
        # UAE cities
        if validated_country == 'UAE':
            if re.search(r'\bdubai\b', job_text_lower):
                return 'Dubai, UAE'
            elif re.search(r'\babu dhabi\b', job_text_lower):
                return 'Abu Dhabi, UAE'
            elif re.search(r'\bsharjah\b', job_text_lower):
                return 'Sharjah, UAE'
            else:
                return 'UAE'
        
        # Saudi cities
        elif validated_country == 'Saudi Arabia':
            if re.search(r'\briyadh\b', job_text_lower):
                return 'Riyadh, Saudi Arabia'
            elif re.search(r'\bjeddah\b', job_text_lower):
                return 'Jeddah, Saudi Arabia'
            elif re.search(r'\bdammam\b', job_text_lower):
                return 'Dammam, Saudi Arabia'
            else:
                return 'Saudi Arabia'
        
        # Qatar cities
        elif validated_country == 'Qatar':
            if re.search(r'\bdoha\b', job_text_lower):
                return 'Doha, Qatar'
            else:
                return 'Qatar'
        
        # UK cities
        elif validated_country == 'United Kingdom':
            if re.search(r'\blondon\b', job_text_lower):
                return 'London, UK'
            elif re.search(r'\bmanchester\b', job_text_lower):
                return 'Manchester, UK'
            elif re.search(r'\bbirmingham\b', job_text_lower):
                return 'Birmingham, UK'
            elif re.search(r'\bedinburgh\b', job_text_lower):
                return 'Edinburgh, UK'
            else:
                return 'United Kingdom'
        
        return f'{validated_country}'
    
    def search_linkedin_jobs(self, keyword: str, location: str, target_country: str) -> List[Dict]:
        """Search LinkedIn jobs with improved location filtering"""
        jobs = []
        
        try:
            # LinkedIn public job search URL
            base_url = "https://www.linkedin.com/jobs/search"
            
            params = {
                'keywords': keyword,
                'location': location,
                'sortBy': 'DD',  # Date descending (newest first)
                'position': '1',
                'pageNum': '0'
            }
            
            url = f"{base_url}?" + urllib.parse.urlencode(params)
            logging.info(f"Searching LinkedIn: '{keyword}' in '{location}' (expecting {target_country})")
            
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find job cards on LinkedIn - try multiple selectors
                job_cards = (
                    soup.find_all('div', {'class': lambda x: x and 'result-card' in x}) or
                    soup.find_all('div', {'class': lambda x: x and 'job-search-card' in x}) or
                    soup.find_all('li', {'class': lambda x: x and 'result-card' in x}) or
                    soup.find_all('div', {'data-entity-urn': True}) or
                    soup.find_all('div', {'class': lambda x: x and 'base-card' in x})
                )
                
                logging.info(f"Found {len(job_cards)} potential job cards")
                
                validated_jobs = 0
                rejected_jobs = 0
                
                for i, card in enumerate(job_cards[:25]):  # Process first 25 cards
                    try:
                        job = self.extract_and_validate_job(card, target_country, location)
                        if job:
                            jobs.append(job)
                            validated_jobs += 1
                            if i < 3:  # Log first few jobs for debugging
                                logging.info(f"✅ Valid job: '{job['title']}' at {job['company']} in {job['location']}")
                        else:
                            rejected_jobs += 1
                            if i < 3:  # Log first few rejections for debugging
                                card_text = card.get_text()[:100].replace('\n', ' ')
                                logging.info(f"❌ Rejected job: {card_text}...")
                    except Exception as e:
                        logging.warning(f"Error processing job card {i}: {e}")
                        continue
                
                logging.info(f"Location validation results: {validated_jobs} valid, {rejected_jobs} rejected for {target_country}")
                
                # Rate limiting
                time.sleep(3)
                
            else:
                logging.warning(f"LinkedIn search returned status {response.status_code}")
                
        except Exception as e:
            logging.error(f"Error searching LinkedIn for {keyword} in {location}: {e}")
        
        logging.info(f"LinkedIn: Found {len(jobs)} VALIDATED jobs for '{keyword}' in {target_country}")
        return jobs
    
    def extract_and_validate_job(self, card, expected_country: str, search_location: str) -> Dict:
        """Extract job info and validate location matches expected country"""
        try:
            # Get all text from the card for analysis
            full_card_text = card.get_text()
            
            # Validate location FIRST
            validated_country = self.validate_job_location(full_card_text)
            
            if validated_country != expected_country:
                # Log the mismatch for debugging
                logging.debug(f"Location mismatch: expected {expected_country}, validated as {validated_country or 'Unknown'}")
                return None
            
            # Extract title
            title_elem = (
                card.find('h3') or 
                card.find('a', {'class': lambda x: x and 'job-title' in x}) or
                card.find('span', {'class': lambda x: x and 'sr-only' in x}) or
                card.select_one('[data-entity-urn] h3') or
                card.select_one('a[href*="/jobs/view/"]')
            )
            
            title = ""
            if title_elem:
                title = title_elem.get_text(strip=True)
                if not title and title_elem.find('a'):
                    title = title_elem.find('a').get_text(strip=True)
            
            if not title or len(title) < 5:
                return None
            
            # Extract company
            company_elem = (
                card.find('h4') or 
                card.find('a', {'class': lambda x: x and 'company' in x}) or
                card.find('span', {'class': lambda x: x and 'company' in x}) or
                card.find('div', {'class': lambda x: x and 'company' in x})
            )
            
            company = "Unknown Company"
            if company_elem:
                company = company_elem.get_text(strip=True)
            
            # Extract URL
            job_url = ""
            link_elem = card.find('a', href=True)
            if link_elem:
                href = link_elem.get('href')
                if href.startswith('/'):
                    job_url = "https://www.linkedin.com" + href
                else:
                    job_url = href
                    
                # Clean LinkedIn URL
                if 'linkedin.com' in job_url and '?' in job_url:
                    job_url = job_url.split('?')[0]
            
            # Extract specific location
            detailed_location = self.extract_detailed_location(full_card_text, validated_country)
            
            # Create job object
            job = {
                'id': f"linkedin:{job_url.split('/')[-1] if job_url else title.replace(' ', '_')}",
                'title': title,
                'company': company,
                'location': detailed_location,
                'country': validated_country,
                'url': job_url,
                'description': full_card_text[:200] + "..." if len(full_card_text) > 200 else full_card_text,
                'posted_date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'LinkedIn'
            }
            
            return job
            
        except Exception as e:
            logging.warning(f"Error extracting job details: {e}")
            return None
    
    def search_all_linkedin_jobs(self) -> List[Dict]:
        """Search LinkedIn for all target positions with strict location validation"""
        all_jobs = []
        
        logging.info("🚀 Starting LinkedIn job search with STRICT location validation")
        
        # Search each keyword in each location
        for keyword in self.finance_keywords:
            for country, search_locations in self.search_locations.items():
                for location in search_locations:
                    
                    jobs = self.search_linkedin_jobs(keyword, location, country)
                    all_jobs.extend(jobs)
                    
                    # Respectful rate limiting
                    time.sleep(4)
        
        # Remove duplicates based on job ID
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job['id'] not in seen_ids:
                seen_ids.add(job['id'])
                unique_jobs.append(job)
        
        # Log summary by country
        country_counts = {}
        for job in unique_jobs:
            country = job['country']
            country_counts[country] = country_counts.get(country, 0) + 1
        
        logging.info(f"Final results by country: {country_counts}")
        logging.info(f"Found {len(unique_jobs)} unique VALIDATED jobs on LinkedIn")
        
        return unique_jobs
    
    def filter_by_companies(self, jobs: List[Dict], target_companies: List[str]) -> List[Dict]:
        """Filter jobs to prioritize companies from Excel list"""
        company_names_lower = [comp.lower() for comp in target_companies]
        
        priority_jobs = []
        other_jobs = []
        
        for job in jobs:
            job_company_lower = job['company'].lower()
            
            # Check if job company matches any target company
            is_target_company = any(
                target_comp in job_company_lower or job_company_lower in target_comp
                for target_comp in company_names_lower
            )
            
            if is_target_company:
                priority_jobs.append(job)
            else:
                other_jobs.append(job)
        
        # Return priority jobs first, then others (limited)
        return priority_jobs + other_jobs[:50]  # Limit other jobs to 50
    
    def send_email(self, new_jobs: List[Dict]):
        """Send email with new LinkedIn job listings"""
        if not new_jobs:
            logging.info("No new jobs found - skipping email")
            return
        
        email_user = os.environ['EMAIL_USER']
        email_pass = os.environ['EMAIL_PASS']
        recipient = os.environ['RECIPIENT_EMAIL']
        
        # Group jobs by country, then by company
        jobs_by_country = {}
        for job in new_jobs:
            country = job['country']
            company = job['company']
            
            if country not in jobs_by_country:
                jobs_by_country[country] = {}
            if company not in jobs_by_country[country]:
                jobs_by_country[country][company] = []
            
            jobs_by_country[country][company].append(job)
        
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = recipient
        msg['Subject'] = f"💼 {len(new_jobs)} VERIFIED Senior Finance Jobs from LinkedIn"
        
        # Create comprehensive HTML email
        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 1000px; margin: 0 auto; line-height: 1.6;">
            <div style="background: linear-gradient(135deg, #0077B5 0%, #005885 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 28px;">LinkedIn Finance Jobs Alert</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">
                    {datetime.now().strftime('%A, %B %d, %Y - 7:00 AM UAE Time')}
                </p>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">
                    ✅ Location Verified • Powered by LinkedIn
                </p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 25px; border-left: 4px solid #28a745;">
                <h3 style="color: #28a745; margin-top: 0;">📊 Today's VERIFIED LinkedIn Results</h3>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;">
                    <div>
                        <p><strong>{len(new_jobs)}</strong> location-verified positions</p>
                        <p><strong>{len(jobs_by_country)}</strong> countries with opportunities</p>
                    </div>
                    <div>
                        <p><strong>{sum(len(companies) for companies in jobs_by_country.values())}</strong> companies hiring</p>
                        <p><strong>Quality:</strong> All locations double-checked</p>
                    </div>
                </div>
            </div>
        """
        
        # Add jobs by country
        for country, companies in jobs_by_country.items():
            country_total = sum(len(jobs) for jobs in companies.values())
            
            html_body += f"""
            <div style="margin: 30px 0;">
                <h2 style="color: #2c3e50; border-bottom: 3px solid #0077B5; padding-bottom: 10px; background-color: #ecf0f1; padding: 15px; margin: 0;">
                    🌍 {country} ({country_total} verified position{'s' if country_total > 1 else ''})
                </h2>
            """
            
            for company, company_jobs in companies.items():
                html_body += f"""
                <div style="margin: 20px 0; padding-left: 20px;">
                    <h3 style="color: #34495e; margin-bottom: 15px;">
                        🏢 {company} ({len(company_jobs)} role{'s' if len(company_jobs) > 1 else ''})
                    </h3>
                """
                
                for job in company_jobs:
                    html_body += f"""
                    <div style="border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 10px 0; background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                        <h4 style="color: #0077B5; margin-top: 0; font-size: 18px;">{job['title']}</h4>
                        <p style="margin: 8px 0; color: #6c757d;">📍 {job['location']} ✅</p>
                        <p style="margin: 8px 0; color: #6c757d; font-size: 14px;">🔗 Source: LinkedIn (Location Verified)</p>
                        <div style="margin-top: 15px;">
                            <a href="{job['url']}" target="_blank" 
                               style="background: linear-gradient(45deg, #0077B5, #005885); color: white; padding: 12px 24px; 
                                      text-decoration: none; border-radius: 25px; display: inline-block; font-weight: 500;">
                                View on LinkedIn →
                            </a>
                        </div>
                    </div>
                    """
                
                html_body += "</div>"
            
            html_body += "</div>"
        
        # Footer
        html_body += f"""
            <div style="background-color: #6c757d; color: white; padding: 25px; text-align: center; border-radius: 0 0 10px 10px; margin-top: 40px;">
                <p style="margin: 0; font-size: 14px;">
                    <strong>LinkedIn Professional Network with Location Validation</strong><br>
                    Strict location filtering • Running daily at 7:00 AM UAE time<br>
                    <em>All job locations verified using regex pattern matching</em>
                </p>
                <p style="margin: 10px 0 0 0; font-size: 12px; opacity: 0.8;">
                    Source: LinkedIn Jobs • Location Verified • {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(email_user, email_pass)
                server.send_message(msg)
            logging.info(f"✅ Email sent successfully to {recipient} with {len(new_jobs)} jobs")
        except Exception as e:
            logging.error(f"❌ Failed to send email: {e}")

def main():
    scraper = LinkedInJobScraper()
    
    logging.info("🔍 Starting LinkedIn job search with STRICT location validation")
    start_time = time.time()
    
    # Load companies from Excel for filtering
    target_companies = scraper.load_companies_from_excel()
    logging.info(f"Loaded {len(target_companies)} target companies for prioritization")
    
    # Load seen jobs
    seen_jobs = scraper.load_seen_jobs()
    initial_count = len(seen_jobs)
    
    # Search LinkedIn for all positions with location validation
    all_jobs = scraper.search_all_linkedin_jobs()
    
    # Filter and prioritize by target companies
    filtered_jobs = scraper.filter_by_companies(all_jobs, target_companies)
    
    # Filter for new jobs only
    new_jobs = [job for job in filtered_jobs if job['id'] not in seen_jobs]
    
    # Update seen jobs
    for job in new_jobs:
        seen_jobs.add(job['id'])
    
    # Save updated seen jobs
    scraper.save_seen_jobs(seen_jobs)
    
    # Send email
    scraper.send_email(new_jobs)
    
    # Final statistics
    end_time = time.time()
    duration = end_time - start_time
    
    logging.info(f"""
    📈 LINKEDIN JOB SEARCH COMPLETE:
    ⏱️  Duration: {duration:.1f} seconds
    🎯 Finance keywords searched: {len(scraper.finance_keywords)}
    🌍 Location searches performed: {sum(len(locs) for locs in scraper.search_locations.values())}
    🏢 Total jobs found: {len(all_jobs)}
    ✨ Jobs after filtering: {len(filtered_jobs)}
    🆕 New jobs found: {len(new_jobs)}
    💾 Total jobs tracked: {len(seen_jobs)}
    📧 Email sent to: kamran.habibollah@gmail.com
    """)

if __name__ == "__main__":
    main()
