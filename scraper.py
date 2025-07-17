import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
import pandas as pd
from datetime import datetime
import time
import concurrent.futures
from threading import Lock
import logging
import re
from urllib.parse import urljoin, urlparse
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MultiCountryJobScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.lock = Lock()
        self.all_jobs = []
        
        # Target countries
        self.target_countries = ['UAE', 'Saudi Arabia', 'Qatar', 'United Kingdom', 'UK']
        
        # Comprehensive senior finance job titles
        self.target_titles = [
            'cfo', 'chief financial officer', 'chief finance officer',
            'finance director', 'finance lead', 'corporate finance director',
            'finance vp', 'finance svp', 'finance team lead',
            'finance and operations lead', 'financial services business development leader',
            'commercial finance lead', 'commercial finance director',
            'commercial finance vp', 'commercial finance svp',
            # Additional senior finance titles
            'group finance director', 'regional finance director', 'head of finance',
            'senior finance director', 'deputy cfo', 'assistant cfo',
            'finance controller', 'group controller', 'regional controller',
            'treasury director', 'head of treasury', 'treasury lead',
            'fp&a director', 'financial planning director', 'budget director',
            'investor relations director', 'ir director', 'head of investor relations',
            'financial reporting director', 'corporate development director',
            'business finance director', 'divisional finance director',
            'finance transformation director', 'finance operations director',
            'chief accounting officer', 'cao', 'head of accounting'
        ]
        
    def load_companies_from_excel(self):
        """Load companies from Excel file and add additional companies"""
        try:
            # Read the Excel file (Column A, no header)
            df = pd.read_excel('Top Companies.xlsx', header=None, names=['company'])
            existing_companies = df['company'].tolist()
            
            logging.info(f"Loaded {len(existing_companies)} companies from Excel file")
            
            # Add additional companies to reach ~100 total
            additional_companies = self.get_additional_companies()
            
            all_companies = existing_companies + additional_companies
            
            # Convert to company configs with career page URLs
            company_configs = []
            for company in all_companies:
                config = self.create_company_config(company)
                if config:
                    company_configs.append(config)
            
            logging.info(f"Total companies configured: {len(company_configs)}")
            return company_configs
            
        except Exception as e:
            logging.error(f"Error loading companies from Excel: {e}")
            return self.get_fallback_companies()
    
    def get_additional_companies(self):
        """Add companies to reach target of ~100"""
        additional = [
            # Major Tech Companies
            'Microsoft', 'Google', 'Amazon', 'Apple', 'Meta', 'Netflix', 'Adobe',
            'Salesforce', 'Oracle', 'SAP', 'IBM', 'Cisco', 'Intel', 'Nvidia',
            
            # Financial Services
            'JPMorgan Chase', 'Goldman Sachs', 'Morgan Stanley', 'BlackRock',
            'Citigroup', 'Bank of America', 'Wells Fargo', 'American Express',
            'Visa', 'Mastercard', 'PayPal', 'Square',
            
            # UAE/GCC Specific
            'Etisalat', 'Du', 'Aramco', 'SABIC', 'Al Rajhi Bank', 'NCB',
            'QNB', 'Ooredoo', 'Zain', 'STC', 'Majid Al Futtaim', 'Emaar',
            'DP World', 'Expo 2020', 'DEWA', 'ADNOC', 'Mubadala',
            
            # UK Companies
            'Barclays', 'HSBC', 'Lloyds', 'Standard Chartered', 'Vodafone',
            'BT Group', 'Tesco', 'Unilever', 'BP', 'Shell', 'AstraZeneca',
            'GSK', 'Rolls-Royce', 'BAE Systems',
            
            # Consulting & Professional Services
            'McKinsey', 'BCG', 'Bain', 'Deloitte', 'PwC', 'EY', 'KPMG',
            'Accenture', 'IBM Consulting'
        ]
        return additional[:37]  # Take 37 to reach ~100 total
    
    def create_company_config(self, company_name):
        """Create configuration for a company including career page URL"""
        try:
            # Common career page patterns
            career_patterns = [
                '/careers', '/jobs', '/career', '/join-us', '/work-with-us',
                '/opportunities', '/talent', '/people', '/about/careers'
            ]
            
            # Try to find the company's main website
            base_url = self.find_company_website(company_name)
            if not base_url:
                return None
            
            # Try different career page URLs
            for pattern in career_patterns:
                career_url = base_url.rstrip('/') + pattern
                if self.test_url_accessible(career_url):
                    return {
                        'name': company_name,
                        'url': career_url,
                        'base_url': base_url,
                        'job_selectors': [
                            '.job-listing', '.job-item', '.position', '.career-item',
                            '[class*="job"]', '[class*="career"]', '[class*="position"]',
                            '.opportunity', '.role', '.opening'
                        ]
                    }
            
            # If no career page found, use main website
            return {
                'name': company_name,
                'url': base_url,
                'base_url': base_url,
                'job_selectors': [
                    '.job-listing', '.job-item', '.position', '.career-item',
                    '[class*="job"]', '[class*="career"]', '[class*="position"]'
                ]
            }
            
        except Exception as e:
            logging.warning(f"Could not create config for {company_name}: {e}")
            return None
    
    def find_company_website(self, company_name):
        """Try to find company website URL"""
        # Simple heuristic - convert company name to likely domain
        company_clean = re.sub(r'[^\w\s]', '', company_name.lower())
        company_clean = company_clean.replace(' ', '')
        
        # Common domain patterns
        domain_patterns = [
            f"https://www.{company_clean}.com",
            f"https://{company_clean}.com", 
            f"https://www.{company_clean}.co.uk",
            f"https://www.{company_clean}.ae",
            f"https://www.{company_clean}.sa"
        ]
        
        for domain in domain_patterns:
            if self.test_url_accessible(domain):
                return domain
        
        # Fallback to search-based approach (simplified)
        return f"https://www.{company_clean}.com"
    
    def test_url_accessible(self, url):
        """Test if URL is accessible"""
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            return response.status_code == 200
        except:
            return False
    
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
    
    def scrape_single_company(self, company_config):
        """Scrape jobs from a single company"""
        try:
            company_name = company_config['name']
            logging.info(f"Scraping {company_name}")
            
            # Random delay to be respectful
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(company_config['url'], timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            jobs_found = []
            
            # Try multiple selectors
            job_elements = []
            for selector in company_config['job_selectors']:
                elements = soup.select(selector)
                if elements:
                    job_elements = elements[:30]  # Limit per selector
                    break
            
            # If no job elements found, try generic selectors
            if not job_elements:
                generic_selectors = ['a[href*="job"]', 'a[href*="career"]', 'div:contains("finance")', 'h3', 'h4']
                for selector in generic_selectors:
                    try:
                        elements = soup.select(selector)
                        if elements:
                            job_elements = elements[:20]
                            break
                    except:
                        continue
            
            # Process found elements
            for element in job_elements:
                try:
                    job = self.extract_job_info(element, company_config)
                    if job and self.is_relevant_job(job):
                        jobs_found.append(job)
                except Exception as e:
                    continue
            
            with self.lock:
                self.all_jobs.extend(jobs_found)
            
            logging.info(f"✅ {company_name}: Found {len(jobs_found)} relevant jobs")
            return jobs_found
            
        except Exception as e:
            logging.error(f"❌ Error scraping {company_config['name']}: {e}")
            return []
    
    def extract_job_info(self, element, company_config):
        """Extract job information from HTML element"""
        # Get text content
        element_text = element.get_text(strip=True)
        
        # Try to find title
        title = None
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
            title = element_text
        elif element.name == 'a':
            title = element_text or element.get('title', '')
        else:
            # Look for title in child elements
            title_elem = element.find(['h1', 'h2', 'h3', 'h4', 'h5', 'a'])
            if title_elem:
                title = title_elem.get_text(strip=True)
        
        if not title or len(title) < 3:
            return None
        
        # Extract URL
        job_url = ''
        if element.name == 'a':
            job_url = element.get('href', '')
        else:
            link_elem = element.find('a')
            if link_elem:
                job_url = link_elem.get('href', '')
        
        if job_url and not job_url.startswith('http'):
            job_url = urljoin(company_config['base_url'], job_url)
        
        return {
            'id': f"{company_config['name']}:{job_url or title}",
            'company': company_config['name'],
            'title': title,
            'url': job_url,
            'location': self.extract_location(element_text),
            'country': self.extract_country(element_text),
            'full_text': element_text
        }
    
    def is_relevant_job(self, job):
        """Check if job matches our criteria"""
        title_lower = job['title'].lower()
        text_lower = job['full_text'].lower()
        
        # Check for finance titles
        has_finance_title = any(title in title_lower for title in self.target_titles)
        
        # Check for target countries
        has_target_country = job['country'] in self.target_countries
        
        return has_finance_title and has_target_country
    
    def extract_location(self, text):
        """Extract specific location from text"""
        text_lower = text.lower()
        
        # UAE locations
        uae_locations = {
            'dubai': 'Dubai, UAE',
            'abu dhabi': 'Abu Dhabi, UAE',
            'sharjah': 'Sharjah, UAE',
            'ajman': 'Ajman, UAE'
        }
        
        # Saudi locations
        saudi_locations = {
            'riyadh': 'Riyadh, Saudi Arabia',
            'jeddah': 'Jeddah, Saudi Arabia',
            'dammam': 'Dammam, Saudi Arabia',
            'khobar': 'Khobar, Saudi Arabia'
        }
        
        # Qatar locations
        qatar_locations = {
            'doha': 'Doha, Qatar',
            'qatar': 'Qatar'
        }
        
        # UK locations
        uk_locations = {
            'london': 'London, UK',
            'manchester': 'Manchester, UK',
            'birmingham': 'Birmingham, UK',
            'edinburgh': 'Edinburgh, UK',
            'glasgow': 'Glasgow, UK'
        }
        
        all_locations = {**uae_locations, **saudi_locations, **qatar_locations, **uk_locations}
        
        for keyword, location in all_locations.items():
            if keyword in text_lower:
                return location
        
        return 'Location TBD'
    
    def extract_country(self, text):
        """Extract country from text"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['uae', 'dubai', 'abu dhabi', 'emirates', 'sharjah']):
            return 'UAE'
        elif any(word in text_lower for word in ['saudi', 'riyadh', 'jeddah', 'ksa']):
            return 'Saudi Arabia'
        elif any(word in text_lower for word in ['qatar', 'doha']):
            return 'Qatar'
        elif any(word in text_lower for word in ['uk', 'united kingdom', 'london', 'manchester', 'birmingham']):
            return 'United Kingdom'
        else:
            return 'Unknown'
    
    def scrape_all_companies(self, companies):
        """Scrape all companies in parallel"""
        logging.info(f"🚀 Starting parallel scraping of {len(companies)} companies")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.scrape_single_company, company): company 
                      for company in companies}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    company = futures[future]
                    logging.error(f"Failed to scrape {company['name']}: {e}")
        
        return self.all_jobs
    
    def send_email(self, new_jobs):
        """Send email with new job listings organized by country and company"""
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
        msg['Subject'] = f"🎯 {len(new_jobs)} New Senior Finance Jobs Across {len(jobs_by_country)} Countries"
        
        # Create comprehensive HTML email
        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 1000px; margin: 0 auto; line-height: 1.6;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 28px;">Senior Finance Jobs Alert</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">
                    {datetime.now().strftime('%A, %B %d, %Y - 7:00 AM UAE Time')}
                </p>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 25px; border-left: 4px solid #28a745;">
                <h3 style="color: #28a745; margin-top: 0;">📊 Today's Summary</h3>
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
                <h2 style="color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; background-color: #ecf0f1; padding: 15px; margin: 0;">
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
                        <h4 style="color: #2980b9; margin-top: 0; font-size: 18px;">{job['title']}</h4>
                        <p style="margin: 8px 0; color: #6c757d;">📍 {job['location']}</p>
                        <div style="margin-top: 15px;">
                            <a href="{job['url']}" target="_blank" 
                               style="background: linear-gradient(45deg, #3498db, #2980b9); color: white; padding: 12px 24px; 
                                      text-decoration: none; border-radius: 25px; display: inline-block; font-weight: 500;">
                                View Position →
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
                    <strong>Automated Daily Monitoring</strong><br>
                    Scanning ~100 companies • Running daily at 7:00 AM UAE time<br>
                    <em>Targeting: CFO, Finance Director, VP Finance roles in UAE, Saudi Arabia, Qatar & UK</em>
                </p>
                <p style="margin: 10px 0 0 0; font-size: 12px; opacity: 0.8;">
                    Powered by GitHub Actions • Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
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
    
    def get_fallback_companies(self):
        """Fallback company list if Excel file fails"""
        companies = [
            'Microsoft', 'Google', 'Amazon', 'Apple', 'Meta', 'Salesforce',
            'Emirates NBD', 'ADNOC', 'Etisalat', 'Aramco', 'SABIC',
            'HSBC', 'Barclays', 'Standard Chartered', 'BP', 'Shell'
        ]
        return [self.create_company_config(company) for company in companies if self.create_company_config(company)]

def main():
    scraper = MultiCountryJobScraper()
    
    logging.info("🔍 Starting multi-country senior finance job search")
    start_time = time.time()
    
    # Load companies
    companies = scraper.load_companies_from_excel()
    logging.info(f"Loaded {len(companies)} companies for monitoring")
    
    # Load seen jobs
    seen_jobs = scraper.load_seen_jobs()
    initial_count = len(seen_jobs)
    
    # Scrape all companies
    all_jobs = scraper.scrape_all_companies(companies)
    
    # Filter for new jobs
    new_jobs = [job for job in all_jobs if job['id'] not in seen_jobs]
    
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
    📈 SCRAPING COMPLETE:
    ⏱️  Duration: {duration:.1f} seconds
    🏢 Companies monitored: {len(companies)}
    🆕 New jobs found: {len(new_jobs)}
    💾 Total jobs tracked: {len(seen_jobs)}
    📧 Email sent to: kamran.habibollah@gmail.com
    """)

if __name__ == "__main__":
    main()
