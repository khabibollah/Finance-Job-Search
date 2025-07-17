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
        
        # LinkedIn location IDs for your target countries
        self.linkedin_locations = {
            'UAE': {
                'Dubai': '105218', 
                'Abu Dhabi': '104769',
                'UAE': '104305'
            },
            'Saudi Arabia': {
                'Riyadh': '106906',
                'Jeddah': '103969', 
                'Saudi Arabia': '103323'
            },
            'Qatar': {
                'Doha': '100961',
                'Qatar': '100876'
            },
            'United Kingdom': {
                'London': '101165',
                'Manchester': '100556',
                'UK': '101282'
            }
        }
        
        # Senior finance keywords for LinkedIn search
        self.finance_keywords = [
            "CFO",
            "Chief Financial Officer", 
            "Finance Director",
            "VP Finance",
            "Finance Lead",
            "Commercial Finance Director",
            "Finance VP",
            "Finance SVP",
            "Treasury Director",
            "FP&A Director",
            "Financial Planning Director",
            "Head of Finance",
            "Regional Finance Director",
            "Group Finance Director",
            "Deputy CFO",
            "Finance Controller",
            "Business Finance Director"
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
    
    def search_linkedin_jobs(self, keyword: str, location_id: str, location_name: str, country: str) -> List[Dict]:
        """Search LinkedIn jobs using their public job search"""
        jobs = []
        
        try:
            # LinkedIn public job search URL
            base_url = "https://www.linkedin.com/jobs/search"
            
            params = {
                'keywords': keyword,
                'location': location_name,
                'locationId': location_id,
                'geoId': location_id,
                'sortBy': 'DD',  # Date descending (newest first)
                'position': '1',
                'pageNum': '0',
                'start': '0'
            }
            
            url = f"{base_url}?" + urllib.parse.urlencode(params)
            logging.info(f"Searching LinkedIn: {keyword} in {location_name}")
            
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find job cards on LinkedIn
                job_cards = soup.find_all('div', {'class': lambda x: x and 'result-card' in x}) or \
                           soup.find_all('div', {'class': lambda x: x and 'job-search-card' in x}) or \
                           soup.find_all('li', {'class': lambda x: x and 'result-card' in x})
                
                logging.info(f"Found {len(job_cards)} job cards on page")
                
                for card in job_cards[:20]:  # Limit to first 20 jobs per search
                    try:
                        job = self.extract_job_from_card(card, country, location_name)
                        if job:
                            jobs.append(job)
                    except Exception as e:
                        logging.warning(f"Error extracting job from card: {e}")
                        continue
                
                # Rate limiting
                time.sleep(2)
                
            else:
                logging.warning(f"LinkedIn search returned status {response.status_code}")
                
        except Exception as e:
            logging.error(f"Error searching LinkedIn for {keyword} in {location_name}: {e}")
        
        logging.info(f"LinkedIn: Found {len(jobs)} jobs for '{keyword}' in {location_name}")
        return jobs
    
    def extract_job_from_card(self, card, country: str, location: str) -> Dict:
        """Extract job information from LinkedIn job card"""
        try:
            # Extract title
            title_elem = card.find('h3') or card.find('a', {'class': lambda x: x and 'job-title' in x}) or \
                        card.find('span', {'class': lambda x: x and 'sr-only' in x})
            
            title = ""
            if title_elem:
                # Try to get text from various elements
                title = title_elem.get_text(strip=True)
                if not title and title_elem.find('a'):
                    title = title_elem.find('a').get_text(strip=True)
            
            if not title or len(title) < 5:
                return None
            
            # Extract company
            company_elem = card.find('h4') or card.find('a', {'class': lambda x: x and 'company' in x}) or \
                          card.find('span', {'class': lambda x: x and 'company' in x})
            
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
            
            # Extract location from text
            card_text = card.get_text()
            extracted_location = self.extract_location_from_text(card_text, location)
            
            # Create job object
            job = {
                'id': f"linkedin:{job_url.split('/')[-1] if job_url else title}",
                'title': title,
                'company': company,
                'location': extracted_location,
                'country': country,
                'url': job_url,
                'description': card_text[:200] + "..." if len(card_text) > 200 else card_text,
                'posted_date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'LinkedIn'
            }
            
            return job
            
        except Exception as e:
            logging.warning(f"Error extracting job details: {e}")
            return None
    
    def extract_location_from_text(self, text: str, default_location: str) -> str:
        """Extract specific location from job card text"""
        text_lower = text.lower()
        
        # UAE locations
        if 'dubai' in text_lower:
            return 'Dubai, UAE'
        elif 'abu dhabi' in text_lower:
            return 'Abu Dhabi, UAE'
        elif 'sharjah' in text_lower:
            return 'Sharjah, UAE'
        
        # Saudi locations
        elif 'riyadh' in text_lower:
            return 'Riyadh, Saudi Arabia'
        elif 'jeddah' in text_lower:
            return 'Jeddah, Saudi Arabia'
        elif 'dammam' in text_lower:
            return 'Dammam, Saudi Arabia'
        
        # Qatar locations
        elif 'doha' in text_lower:
            return 'Doha, Qatar'
        elif 'qatar' in text_lower and 'doha' not in text_lower:
            return 'Qatar'
        
        # UK locations
        elif 'london' in text_lower:
            return 'London, UK'
        elif 'manchester' in text_lower:
            return 'Manchester, UK'
        elif 'birmingham' in text_lower:
            return 'Birmingham, UK'
        elif 'edinburgh' in text_lower:
            return 'Edinburgh, UK'
        
        # Default to the search location
        return default_location
    
    def search_all_linkedin_jobs(self) -> List[Dict]:
        """Search LinkedIn for all target positions across all locations"""
        all_jobs = []
        
        logging.info("🚀 Starting comprehensive LinkedIn job search")
        
        # Search each keyword in each location
        for keyword in self.finance_keywords:
            for country, locations in self.linkedin_locations.items():
                for location_name, location_id in locations.items():
                    
                    jobs = self.search_linkedin_jobs(keyword, location_id, location_name, country)
                    all_jobs.extend(jobs)
                    
                    # Be respectful with rate limiting
                    time.sleep(3)
        
        # Remove duplicates based on job ID
        seen_ids = set()
        unique_jobs = []
        for job in all_jobs:
            if job['id'] not in seen_ids:
                seen_ids.add(job['id'])
                unique_jobs.append(job)
        
        logging.info(f"Found {len(unique_jobs)} unique jobs on LinkedIn")
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
        msg['Subject'] = f"💼 {len(new_jobs)} New Senior Finance Jobs from LinkedIn"
        
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
                    Powered by LinkedIn Job Search
                </p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 25px; border-left: 4px solid #0077B5;">
                <h3 style="color: #0077B5; margin-top: 0;">📊 Today's LinkedIn Results</h3>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;">
                    <div>
                        <p><strong>{len(new_jobs)}</strong> new senior finance positions</p>
                        <p><strong>{len(jobs_by_country)}</strong> countries with opportunities</p>
                    </div>
                    <div>
                        <p><strong>{sum(len(companies) for companies in jobs_by_country.values())}</strong> companies hiring</p>
                        <p><strong>Focus:</strong> CFO, Finance Director, VP Finance roles</p>
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
                    🌍 {country} ({country_total} position{'s' if country_total > 1 else ''})
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
                        <p style="margin: 8px 0; color: #6c757d;">📍 {job['location']}</p>
                        <p style="margin: 8px 0; color: #6c757d; font-size: 14px;">🔗 Source: LinkedIn</p>
                        <p style="margin: 8px 0; color: #6c757d; font-size: 13px;">{job['description'][:150]}...</p>
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
                    <strong>LinkedIn Professional Network</strong><br>
                    Advanced job search • Running daily at 7:00 AM UAE time<br>
                    <em>CFO, Finance Director, VP Finance roles in UAE, Saudi Arabia, Qatar & UK</em>
                </p>
                <p style="margin: 10px 0 0 0; font-size: 12px; opacity: 0.8;">
                    Source: LinkedIn Jobs • Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
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
    
    logging.info("🔍 Starting LinkedIn-focused job search for senior finance positions")
    start_time = time.time()
    
    # Load companies from Excel for filtering
    target_companies = scraper.load_companies_from_excel()
    logging.info(f"Loaded {len(target_companies)} target companies for prioritization")
    
    # Load seen jobs
    seen_jobs = scraper.load_seen_jobs()
    initial_count = len(seen_jobs)
    
    # Search LinkedIn for all positions
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
    🌍 Locations searched: {sum(len(locs) for locs in scraper.linkedin_locations.values())}
    🏢 Total jobs found: {len(all_jobs)}
    ✨ Jobs after filtering: {len(filtered_jobs)}
    🆕 New jobs found: {len(new_jobs)}
    💾 Total jobs tracked: {len(seen_jobs)}
    📧 Email sent to: kamran.habibollah@gmail.com
    """)

if __name__ == "__main__":
    main()
