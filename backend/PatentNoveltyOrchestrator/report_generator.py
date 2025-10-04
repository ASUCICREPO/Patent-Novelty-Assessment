#!/usr/bin/env python3
"""
Patent Novelty Report Generator. Generates professional PDF reports from DynamoDB data using ReportLab.
"""
import os
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


class PatentNoveltyReportGenerator:
    """Generates professional PDF reports for patent novelty assessments."""
    
    def __init__(self, pdf_filename: str):
        self.pdf_filename = pdf_filename
        self.data = {
            'keywords': {},
            'patents': [],
            'articles': []
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
            
            print(f"Data fetched: {len(self.data['patents'])} patents, {len(self.data['articles'])} articles")
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
        """Fetch top 8 patent results sorted by relevance score."""
        try:
            table = self.dynamodb.Table(RESULTS_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename)
            )
            
            patents = response['Items']
            
            # Sort by relevance_score (descending)
            patents_sorted = sorted(
                patents,
                key=lambda x: float(x.get('relevance_score', 0)),
                reverse=True
            )
            
            # Return top 8
            return patents_sorted[:8]
            
        except Exception as e:
            print(f"Error fetching patents: {e}")
            return []
    
    def _fetch_article_results(self) -> List[Dict[str, Any]]:
        """Fetch top 8 article results sorted by relevance score."""
        try:
            table = self.dynamodb.Table(ARTICLES_TABLE)
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(self.pdf_filename)
            )
            
            articles = response['Items']
            
            # Sort by relevance_score if available, otherwise by citation_count
            articles_sorted = sorted(
                articles,
                key=lambda x: float(x.get('relevance_score', x.get('citation_count', 0))),
                reverse=True
            )
            
            # Return top 8
            return articles_sorted[:8]
            
        except Exception as e:
            print(f"Error fetching articles: {e}")
            return []
    
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
        story.append(Paragraph("*This report is generated by AI Model, manual review required*", subtitle_style))
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
            [Paragraph('Search Tools:', bold_style), Paragraph('PatentView patent search, Semantic Scholar', normal_style)]
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
        
        if self.data['patents']:
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
                patent_table_data.append([
                    Paragraph(str(idx), cell_style),
                    Paragraph(patent.get('patent_number', 'N/A'), cell_style),
                    Paragraph(patent.get('patent_inventors', 'Data not available'), cell_style),
                    Paragraph(patent.get('patent_assignees', 'Data not available'), cell_style),
                    Paragraph(patent.get('patent_title', 'N/A'), cell_style)
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
        else:
            story.append(Paragraph("No patent results found.", styles['Normal']))
        
        story.append(Spacer(1, 0.3*inch))
        
        # Add Literature Search Results
        story.append(Paragraph("Literature Search Results", heading_style))
        
        if self.data['articles']:
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
                
                article_table_data.append([
                    Paragraph(str(idx), cell_style),
                    Paragraph(article.get('journal', 'N/A'), cell_style),
                    Paragraph(year, cell_style),
                    Paragraph(article.get('authors', 'N/A'), cell_style),
                    Paragraph(article.get('article_title', 'N/A'), cell_style)
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
        else:
            story.append(Paragraph("No literature results found.", styles['Normal']))
        
        # Add footer note
        story.append(Spacer(1, 0.5*inch))
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
    
    def generate_and_upload_report(self) -> Dict[str, Any]:
        """Main method to generate and upload report."""
        try:
            # Fetch data
            if not self.fetch_all_data():
                return {
                    'success': False,
                    'error': 'Failed to fetch data from DynamoDB'
                }
            
            # Generate PDF
            pdf_buffer = self.generate_pdf()
            
            # Upload to S3
            s3_path = self.upload_to_s3(pdf_buffer)
            
            return {
                'success': True,
                'report_path': s3_path,
                'message': f'Report generated successfully for case {self.pdf_filename}'
            }
            
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
