#!/usr/bin/env python3
"""
Patent Novelty Report Generator. Generates professional PDF reports from DynamoDB data using ReportLab.
"""
import os
import re
import boto3
from datetime import datetime
from typing import Dict, Any, List, Optional
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
BUCKET_NAME = os.getenv('BUCKET_NAME')
KEYWORDS_TABLE = os.getenv('KEYWORDS_TABLE_NAME')
RESULTS_TABLE = os.getenv('RESULTS_TABLE_NAME')
ARTICLES_TABLE = os.getenv('ARTICLES_TABLE_NAME')
COMMERCIAL_ASSESSMENT_TABLE = os.getenv('COMMERCIAL_ASSESSMENT_TABLE_NAME')


class PatentNoveltyReportGenerator:
    """Generates professional PDF reports for patent novelty assessments."""
    
    def __init__(self, pdf_filename: str):
        self.pdf_filename = pdf_filename
        self.data = {
            'keywords': {},
            'patents': [],
            'articles': [],
            'eca': None
        }
        self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)
    
    def fetch_all_data(self) -> bool:
        """Fetch data from all DynamoDB tables."""
        try:
            print(f"Fetching data for case: {self.pdf_filename}")
            
            # Fetch keywords data
            self.data['keywords'] = self._fetch_keywords_data()
            
            # Fetch patent results (top 8 by relevance)
            self.data['patents'] = self._fetch_patent_results()
            
            # Fetch article results (top 8 by relevance)
            self.data['articles'] = self._fetch_article_results()
            
            # Fetch ECA data
            self.data['eca'] = self._fetch_eca_data()
            
            print(f"Data fetched: {len(self.data['patents'])} patents, {len(self.data['articles'])} articles, ECA: {self.data['eca'] is not None}")
            return True
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            return False
    
    def _fetch_keywords_data(self) -> Dict[str, Any]:
        """Fetch keywords and invention details from DynamoDB."""
        try:
            table = self.dynamodb.Table(KEYWORDS_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename),
                ScanIndexForward=False,
                Limit=1
            )
            
            if response['Items']:
                item = response['Items'][0]
                return {
                    'title': item.get('title', 'Unknown Title'),
                    'technology_description': item.get('technology_description', 'Not available'),
                    'technology_applications': item.get('technology_applications', 'Not available'),
                    'keywords': item.get('keywords', 'Not available')
                }
            else:
                return {
                    'title': 'Unknown Title',
                    'technology_description': 'Not available',
                    'technology_applications': 'Not available',
                    'keywords': 'Not available'
                }
        except Exception as e:
            print(f"Error fetching keywords: {e}")
            return {
                'title': 'Error loading data',
                'technology_description': 'Error loading data',
                'technology_applications': 'Error loading data',
                'keywords': 'Error loading data'
            }
    
    def _fetch_patent_results(self) -> List[Dict[str, Any]]:
        """Fetch top 8 patent results marked for report inclusion."""
        try:
            table = self.dynamodb.Table(RESULTS_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename)
            )
            
            patents = response['Items']
            
            # Filter to only patents marked for report (add_to_report = "Yes")
            patents_for_report = [p for p in patents if p.get('add_to_report') == 'Yes']
            
            # Sort by relevance_score (descending)
            patents_sorted = sorted(
                patents_for_report,
                key=lambda x: float(x.get('relevance_score', 0)),
                reverse=True
            )
            
            # Return top 8
            return patents_sorted[:8]
            
        except Exception as e:
            print(f"Error fetching patents: {e}")
            return []
    
    def _fetch_article_results(self) -> List[Dict[str, Any]]:
        """Fetch top 8 article results marked for report inclusion."""
        try:
            table = self.dynamodb.Table(ARTICLES_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename)
            )
            
            articles = response['Items']
            
            # Filter to only articles marked for report (add_to_report = "Yes")
            articles_for_report = [a for a in articles if a.get('add_to_report') == 'Yes']
            
            # Sort by relevance_score if available, otherwise by citation_count
            articles_sorted = sorted(
                articles_for_report,
                key=lambda x: float(x.get('relevance_score', x.get('citation_count', 0))),
                reverse=True
            )
            
            # Return top 8
            return articles_sorted[:8]
            
        except Exception as e:
            print(f"Error fetching articles: {e}")
            return []
    
    def _fetch_eca_data(self) -> Optional[Dict[str, Any]]:
        """Fetch early commercial assessment data from DynamoDB."""
        try:
            if not COMMERCIAL_ASSESSMENT_TABLE:
                print("COMMERCIAL_ASSESSMENT_TABLE_NAME not configured")
                return None
                
            table = self.dynamodb.Table(COMMERCIAL_ASSESSMENT_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename),
                ScanIndexForward=False,
                Limit=1
            )
            
            if response['Items']:
                return response['Items'][0]
            else:
                print(f"No ECA data found for {self.pdf_filename}")
                return None
                
        except Exception as e:
            print(f"Error fetching ECA data: {e}")
            return None
    
    def generate_pdf(self) -> BytesIO:
        """Generate PDF report using ReportLab."""
        print("Generating PDF report...")
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Container for PDF elements
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=6,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.red,
            fontName='Helvetica-Oblique',
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=10,
            spaceBefore=15
        )
        
        # Add title
        story.append(Paragraph("OTC Patent and Technical Literature Search", title_style))
        story.append(Paragraph("*This report is generated by AI, manual review required*", subtitle_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Add case information with text wrapping
        normal_style = ParagraphStyle(
            'CaseNormal',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica'
        )
        
        bold_style = ParagraphStyle(
            'CaseBold',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold'
        )
        
        case_data = [
            [Paragraph('Case:', bold_style), Paragraph(self.pdf_filename, normal_style)],
            [Paragraph('Title:', bold_style), Paragraph(self.data['keywords'].get('title', 'Not available'), normal_style)],
            [Paragraph('Technology Description:', bold_style), Paragraph(self.data['keywords'].get('technology_description', 'Not available'), normal_style)],
            [Paragraph('Technology Application:', bold_style), Paragraph(self.data['keywords'].get('technology_applications', 'Not available'), normal_style)],
            [Paragraph('Keywords:', bold_style), Paragraph(self.data['keywords'].get('keywords', 'Not available'), normal_style)],
            [Paragraph('Search Tools:', bold_style), Paragraph('PatentView, Semantic Scholar', normal_style)]
        ]
        
        case_table = Table(case_data, colWidths=[1.5*inch, 5*inch])
        case_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(case_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Add Patent Search Results
        story.append(Paragraph("Patent Search Results", heading_style))
        
        if not self.data['patents']:
            story.append(Paragraph("No patents selected for report. Please mark patents with 'add_to_report: Yes' in DynamoDB.", styles['Normal']))
        else:
            # Style for table cells
            cell_style = ParagraphStyle(
                'TableCell',
                parent=styles['Normal'],
                fontSize=8,
                fontName='Helvetica',
                leading=10
            )
            
            header_style = ParagraphStyle(
                'TableHeader',
                parent=styles['Normal'],
                fontSize=9,
                fontName='Helvetica-Bold',
                textColor=colors.whitesmoke,
                alignment=TA_CENTER
            )
            
            patent_table_data = [[
                Paragraph('#', header_style),
                Paragraph('Number', header_style),
                Paragraph('Inventor(s)', header_style),
                Paragraph('Assignee', header_style),
                Paragraph('Title', header_style)
            ]]
            
            for idx, patent in enumerate(self.data['patents'], 1):
                # Get patent title and URL
                patent_title = patent.get('patent_title', 'N/A')
                google_url = patent.get('google_patents_url', '')
                
                # Create hyperlinked title if URL exists
                if google_url and google_url.strip():
                    title_with_link = f'<a href="{google_url}" color="blue"><u>{patent_title}</u></a>'
                else:
                    title_with_link = patent_title
                
                patent_table_data.append([
                    Paragraph(str(idx), cell_style),
                    Paragraph(patent.get('patent_number', 'N/A'), cell_style),
                    Paragraph(patent.get('patent_inventors', 'Data not available'), cell_style),
                    Paragraph(patent.get('patent_assignees', 'Data not available'), cell_style),
                    Paragraph(title_with_link, cell_style)
                ])
            
            patent_table = Table(patent_table_data, colWidths=[0.3*inch, 0.9*inch, 1.5*inch, 1.5*inch, 2.3*inch])
            patent_table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.HexColor('#edf2f7')]),
                # Grid
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(patent_table)
        
        story.append(Spacer(1, 0.3*inch))
        
        # Add Literature Search Results
        story.append(Paragraph("Literature Search Results", heading_style))
        
        if not self.data['articles']:
            story.append(Paragraph("No articles selected for report. Please mark articles with 'add_to_report: Yes' in DynamoDB.", styles['Normal']))
        else:
            # Style for table cells
            cell_style = ParagraphStyle(
                'TableCell',
                parent=styles['Normal'],
                fontSize=8,
                fontName='Helvetica',
                leading=10
            )
            
            header_style = ParagraphStyle(
                'TableHeader',
                parent=styles['Normal'],
                fontSize=9,
                fontName='Helvetica-Bold',
                textColor=colors.whitesmoke,
                alignment=TA_CENTER
            )
            
            article_table_data = [[
                Paragraph('#', header_style),
                Paragraph('Journal Name', header_style),
                Paragraph('Year', header_style),
                Paragraph('Author', header_style),
                Paragraph('Title', header_style)
            ]]
            
            for idx, article in enumerate(self.data['articles'], 1):
                # Extract year from published_date
                pub_date = article.get('published_date', '')
                year = pub_date[:4] if pub_date and len(pub_date) >= 4 else 'N/A'
                
                # Get article title and URLs
                article_title = article.get('article_title', 'N/A')
                open_access_url = article.get('open_access_pdf_url', '')
                article_url = article.get('article_url', '')
                
                # Prioritize open_access_pdf_url, fallback to article_url
                if open_access_url and open_access_url.strip():
                    final_url = open_access_url
                elif article_url and article_url.strip():
                    final_url = article_url
                else:
                    final_url = ''
                
                # Create hyperlinked title if URL exists
                if final_url:
                    title_with_link = f'<a href="{final_url}" color="blue"><u>{article_title}</u></a>'
                else:
                    title_with_link = article_title
                
                article_table_data.append([
                    Paragraph(str(idx), cell_style),
                    Paragraph(article.get('journal', 'N/A'), cell_style),
                    Paragraph(year, cell_style),
                    Paragraph(article.get('authors', 'N/A'), cell_style),
                    Paragraph(title_with_link, cell_style)
                ])
            
            article_table = Table(article_table_data, colWidths=[0.3*inch, 1.5*inch, 0.5*inch, 1.5*inch, 2.7*inch])
            article_table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.HexColor('#edf2f7')]),
                # Grid
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(article_table)
        
        story.append(Spacer(1, 0.3*inch))
        
        # Add Detailed Prior Art Analysis (Abstracts)
        story.append(Paragraph("Detailed Prior Art Analysis", heading_style))
        
        # Combine patents and articles for abstract table
        combined_results = []
        
        # Add patents first
        for idx, patent in enumerate(self.data['patents'], 1):
            combined_results.append({
                'number': idx,
                'assignee_author': patent.get('patent_assignees', 'Data not available'),
                'title': patent.get('patent_title', 'Title not available'),
                'abstract': patent.get('patent_abstract', 'Abstract not available'),
                'url': patent.get('google_patents_url', '')
            })
        
        # Add articles after patents
        start_idx = len(self.data['patents']) + 1
        for idx, article in enumerate(self.data['articles'], start_idx):
            # Get article URLs - prioritize open_access_pdf_url
            open_access_url = article.get('open_access_pdf_url', '')
            article_url = article.get('article_url', '')
            
            # Prioritize open_access_pdf_url, fallback to article_url
            if open_access_url and open_access_url.strip():
                final_url = open_access_url
            elif article_url and article_url.strip():
                final_url = article_url
            else:
                final_url = ''
            
            combined_results.append({
                'number': idx,
                'assignee_author': article.get('authors', 'Authors not available'),
                'title': article.get('article_title', 'Title not available'),
                'abstract': article.get('abstract', 'Abstract not available'),
                'url': final_url
            })
        
        if combined_results:
            # Styles for abstract table
            abstract_cell_style = ParagraphStyle(
                'AbstractCell',
                parent=styles['Normal'],
                fontSize=7,
                fontName='Helvetica',
                leading=9
            )
            
            abstract_title_style = ParagraphStyle(
                'AbstractTitle',
                parent=styles['Normal'],
                fontSize=8,
                fontName='Helvetica-Bold',
                leading=10,
                spaceAfter=4
            )
            
            abstract_header_style = ParagraphStyle(
                'AbstractHeader',
                parent=styles['Normal'],
                fontSize=9,
                fontName='Helvetica-Bold',
                textColor=colors.whitesmoke,
                alignment=TA_CENTER
            )
            
            abstract_table_data = [[
                Paragraph('#', abstract_header_style),
                Paragraph('Assignee/Author', abstract_header_style),
                Paragraph('Title & Abstract', abstract_header_style)
            ]]
            
            for item in combined_results:
                # Combine title (bold) and abstract in one cell
                # Add hyperlink to title if URL exists
                if item.get('url') and item['url'].strip():
                    title_html = f'<b><a href="{item["url"]}" color="blue"><u>{item["title"]}</u></a></b>'
                else:
                    title_html = f"<b>{item['title']}</b>"
                
                title_and_abstract = f"{title_html}<br/><br/>{item['abstract']}"
                
                abstract_table_data.append([
                    Paragraph(str(item['number']), abstract_cell_style),
                    Paragraph(item['assignee_author'], abstract_cell_style),
                    Paragraph(title_and_abstract, abstract_cell_style)
                ])
            
            abstract_table = Table(abstract_table_data, colWidths=[0.3*inch, 1.5*inch, 4.7*inch])
            abstract_table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f7fafc'), colors.HexColor('#edf2f7')]),
                # Grid
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(abstract_table)
        else:
            story.append(Paragraph("No prior art results available for detailed analysis.", styles['Normal']))
        
        # Add legal notice
        story.append(Spacer(1, 0.5*inch))
        
        notice_style = ParagraphStyle(
            'Notice',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#333333'),
            alignment=TA_LEFT,
            leading=11,
            spaceBefore=10,
            spaceAfter=10
        )
        
        legal_notice = """<b>Notice:</b> This report is technical in nature, and does not constitute a legal opinion. 
        The characterization, paraphrasing, quotation, inclusion or omission of any prior art with regard to this report 
        represents the personal, non-legal judgment of the AI system involved in the preparation of this report. 
        Therefore, the content of this report, including the characterization, paraphrasing, quotation, inclusion or 
        omission of any prior art, should not be construed as having any legal weight nor of being legally dispositive 
        in any manner."""
        
        story.append(Paragraph(legal_notice, notice_style))
        
        # Add timestamp footer
        story.append(Spacer(1, 0.2*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            f"Report generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Generated by AI - Manual Review Required",
            footer_style
        ))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF bytes
        buffer.seek(0)
        print("PDF generated successfully")
        return buffer
    

    def upload_to_s3(self, pdf_buffer: BytesIO) -> str:
        """Upload PDF to S3 reports/ folder."""
        try:
            report_filename = f"{self.pdf_filename}_report.pdf"
            s3_key = f"reports/{report_filename}"
            
            print(f"Uploading to S3: {s3_key}")
            
            self.s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=pdf_buffer.getvalue(),
                ContentType='application/pdf'
            )
            
            s3_path = f"s3://{BUCKET_NAME}/{s3_key}"
            print(f"Report uploaded: {s3_path}")
            return s3_path
            
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            raise
    
    def generate_eca_pdf(self) -> Optional[BytesIO]:
        """Generate Early Commercial Assessment PDF report."""
        if not self.data['eca']:
            print("No ECA data available, skipping ECA report")
            return None
            
        print("Generating ECA PDF report...")
        
        # Create PDF in memory
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Container for PDF elements
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=6,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.red,
            fontName='Helvetica-Oblique',
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        # Add title
        story.append(Paragraph("Early Commercial Assessment Report", title_style))
        story.append(Paragraph("*This report is generated by AI, manual review required*", subtitle_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Case information
        normal_style = ParagraphStyle(
            'CaseNormal',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica'
        )
        
        bold_style = ParagraphStyle(
            'CaseBold',
            parent=styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold'
        )
        
        case_data = [
            [Paragraph('Case:', bold_style), Paragraph(self.pdf_filename, normal_style)],
            [Paragraph('Title:', bold_style), Paragraph(self.data['keywords'].get('title', 'Not available'), normal_style)]
        ]
        
        case_table = Table(case_data, colWidths=[1.5*inch, 5*inch])
        case_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(case_table)
        story.append(Spacer(1, 0.3*inch))
        
        # ECA sections in 2-column table format
        eca_data = self.data['eca']
        
        section_style = ParagraphStyle(
            'SectionLabel',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1a365d')
        )
        
        content_style = ParagraphStyle(
            'SectionContent',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica',
            leading=11,
            spaceBefore=0,
            spaceAfter=0
        )
        
        def format_text_for_pdf(text: str) -> str:
            """
            Convert plain text with line breaks to HTML for ReportLab Paragraph.
            Preserves paragraph breaks and formatting from DynamoDB.
            Truncates text if too long to fit on PDF page.
            """
            if not text or text == 'Not available':
                return text
            
            # TRUNCATE if too long to prevent PDF overflow errors
            MAX_CHARS = 2000  # Roughly 300-400 words - fits comfortably on page
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS].rsplit(' ', 1)[0] + '... (content truncated to fit page)'
            
            # Replace double line breaks with paragraph breaks
            text = text.replace('\n\n', '<br/><br/>')
            
            # Replace single line breaks with line breaks (but keep them softer)
            text = text.replace('\n', '<br/>')
            
            # Escape any HTML special characters (except our <br/> tags)
            # This prevents issues with < > & in the text
            text = text.replace('&', '&amp;')
            text = text.replace('<br/>', '|||BR|||')  # Temporarily protect our breaks
            text = text.replace('<', '&lt;')
            text = text.replace('>', '&gt;')
            text = text.replace('|||BR|||', '<br/>')  # Restore breaks
            
            # Make URLs blue colored (not clickable, just blue text)
            # Find all URLs (http:// or https://)
            url_pattern = r'(https?://[^\s<>]+)'
            text = re.sub(url_pattern, r'<font color="#0000FF">\1</font>', text)
            
            return text
        
        # Define the 10 sections
        sections = [
            ('Problem Solved', format_text_for_pdf(eca_data.get('problem_solved', 'Not available'))),
            ('Solution Offered', format_text_for_pdf(eca_data.get('solution_offered', 'Not available'))),
            ('Non-Confidential Marketing Abstract', format_text_for_pdf(eca_data.get('non_confidential_abstract', 'Not available'))),
            ('Technology Details', format_text_for_pdf(eca_data.get('technology_details', 'Not available'))),
            ('Potential Applications', format_text_for_pdf(eca_data.get('potential_applications', 'Not available'))),
            ('Market Overview', format_text_for_pdf(eca_data.get('market_overview', 'Not available'))),
            ('Competition', format_text_for_pdf(eca_data.get('competition', 'Not available'))),
            ('Potential Licensees', format_text_for_pdf(eca_data.get('potential_licensees', 'Not available'))),
            ('Key Commercialization Challenges', format_text_for_pdf(eca_data.get('key_challenges', 'Not available'))),
            ('Key Assumptions', format_text_for_pdf(eca_data.get('key_assumptions', 'Not available'))),
            ('Key Companies', format_text_for_pdf(eca_data.get('key_companies', 'Not available')))
        ]
        
        # Create table data
        eca_table_data = []
        for label, content in sections:
            eca_table_data.append([
                Paragraph(label, section_style),
                Paragraph(content, content_style)
            ])
        
        # Create table with compact spacing
        eca_table = Table(eca_table_data, colWidths=[2*inch, 4.5*inch], repeatRows=0, spaceBefore=0, spaceAfter=0)
        eca_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f7fafc'), colors.HexColor('#edf2f7')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(eca_table)
        
        # Add legal notice
        story.append(Spacer(1, 0.3*inch))
        
        notice_style = ParagraphStyle(
            'Notice',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#333333'),
            alignment=TA_LEFT,
            leading=11,
            spaceBefore=10,
            spaceAfter=10
        )
        
        legal_notice = """<b>Notice:</b> This report is technical in nature, and does not constitute a legal opinion. 
        The characterization, paraphrasing, quotation, inclusion or omission of any information with regard to this report 
        represents the personal, non-legal judgment of the AI system involved in the preparation of this report. 
        Therefore, the content of this report should not be construed as having any legal weight nor of being legally dispositive 
        in any manner."""
        
        story.append(Paragraph(legal_notice, notice_style))
        
        # Add timestamp footer
        story.append(Spacer(1, 0.2*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            f"Report generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Generated by AI - Manual Review Required",
            footer_style
        ))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF bytes
        buffer.seek(0)
        print("ECA PDF generated successfully")
        return buffer
    
    def upload_eca_to_s3(self, pdf_buffer: BytesIO) -> str:
        """Upload ECA PDF to S3 reports/ folder."""
        try:
            report_filename = f"{self.pdf_filename}_eca_report.pdf"
            s3_key = f"reports/{report_filename}"
            
            print(f"Uploading ECA report to S3: {s3_key}")
            
            self.s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                Body=pdf_buffer.getvalue(),
                ContentType='application/pdf'
            )
            
            s3_path = f"s3://{BUCKET_NAME}/{s3_key}"
            print(f"ECA report uploaded: {s3_path}")
            return s3_path
            
        except Exception as e:
            print(f"Error uploading ECA report to S3: {e}")
            raise

    def generate_and_upload_report(self) -> Dict[str, Any]:
        """Main method to generate and upload both reports."""
        try:
            # Fetch data
            if not self.fetch_all_data():
                return {
                    'success': False,
                    'error': 'Failed to fetch data from DynamoDB'
                }
            
            results = {
                'success': True,
                'novelty_report': None,
                'eca_report': None
            }
            
            # Generate Novelty Report
            if self.data['patents'] or self.data['articles']:
                try:
                    pdf_buffer = self.generate_pdf()
                    s3_path = self.upload_to_s3(pdf_buffer)
                    results['novelty_report'] = {
                        'success': True,
                        'report_path': s3_path,
                        'message': f'Novelty report generated successfully for case {self.pdf_filename}'
                    }
                except Exception as e:
                    results['novelty_report'] = {
                        'success': False,
                        'error': f'Error generating novelty report: {str(e)}'
                    }
            else:
                results['novelty_report'] = {
                    'success': False,
                    'error': 'No patent or article data available for novelty report'
                }
            
            # Generate ECA Report
            if self.data['eca']:
                try:
                    eca_buffer = self.generate_eca_pdf()
                    if eca_buffer:
                        eca_s3_path = self.upload_eca_to_s3(eca_buffer)
                        results['eca_report'] = {
                            'success': True,
                            'report_path': eca_s3_path,
                            'message': f'ECA report generated successfully for case {self.pdf_filename}'
                        }
                    else:
                        results['eca_report'] = {
                            'success': False,
                            'error': 'ECA PDF generation returned None'
                        }
                except Exception as e:
                    results['eca_report'] = {
                        'success': False,
                        'error': f'Error generating ECA report: {str(e)}'
                    }
            else:
                results['eca_report'] = {
                    'success': False,
                    'error': 'No ECA data available for this case'
                }
            
            # Overall success if at least one report generated
            results['success'] = (
                (results['novelty_report'] and results['novelty_report'].get('success')) or
                (results['eca_report'] and results['eca_report'].get('success'))
            )
            
            return results
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


def generate_report(pdf_filename: str) -> Dict[str, Any]:
    """
    Convenience function to generate a patent novelty report.
    """
    generator = PatentNoveltyReportGenerator(pdf_filename)
    return generator.generate_and_upload_report()
