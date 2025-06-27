# main.py - Railway deployment ready
from flask import Flask, request, jsonify, render_template_string
import base64
import json
import os
import tempfile
import logging
from datetime import datetime
import anthropic
import PyPDF2
import docx
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class RegulatoryAnalyzer:
    def __init__(self, anthropic_api_key: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        
    def parse_file(self, file_path: str) -> str:
        """Parse different file types and extract text"""
        file_path = Path(file_path)
        
        try:
            if file_path.suffix.lower() == '.pdf':
                return self._parse_pdf(file_path)
            elif file_path.suffix.lower() == '.docx':
                return self._parse_docx(file_path)
            elif file_path.suffix.lower() == '.txt':
                return self._parse_txt(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_path.suffix}")
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {str(e)}")
            raise

    def _parse_pdf(self, file_path: Path) -> str:
        """Extract text from PDF"""
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text

    def _parse_docx(self, file_path: Path) -> str:
        """Extract text from DOCX"""
        doc = docx.Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text

    def _parse_txt(self, file_path: Path) -> str:
        """Extract text from TXT"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    def analyze_document(self, document_text: str) -> dict:
        """Use Claude to analyze the regulatory document"""
        
        analysis_prompt = f"""
        Please analyze this regulatory warning letter or notice for internal audit purposes. 
        
        Provide a structured analysis in JSON format with the following sections:

        1. document_type: Type of regulatory document (warning letter, notice, citation, etc.)
        2. regulatory_body: Which agency issued this (FDA, OSHA, EPA, etc.)
        3. severity_level: High/Medium/Low based on language and consequences mentioned
        4. key_violations: List of main violations or issues identified
        5. compliance_areas: Specific regulatory areas affected (GMP, safety, environmental, etc.)
        6. deadlines: Any response or corrective action deadlines mentioned
        7. potential_penalties: Financial penalties or other consequences mentioned
        8. audit_focus_areas: Specific areas internal audit should prioritize based on this notice
        9. recommended_actions: Immediate and long-term actions to address issues
        10. risk_assessment: Overall risk level and potential business impact
        11. similar_patterns: Any patterns that might indicate systemic issues
        12. executive_summary: 2-3 sentence summary for leadership

        Document text:
        {document_text[:15000]}
        
        Respond only with valid JSON.
        """

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[{
                    "role": "user", 
                    "content": analysis_prompt
                }]
            )
            
            # Parse the JSON response
            analysis_result = json.loads(response.content[0].text)
            
            # Add metadata
            analysis_result['analysis_timestamp'] = datetime.now().isoformat()
            analysis_result['document_length'] = len(document_text)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in document analysis: {str(e)}")
            raise

# Initialize analyzer with API key from environment
analyzer = RegulatoryAnalyzer(os.getenv('ANTHROPIC_API_KEY'))

@app.route('/')
def home():
    """Simple home page to test the service"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Regulatory Document Analyzer</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .status { padding: 20px; background: #e8f5e8; border-radius: 5px; margin: 20px 0; }
            .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .method { color: #0066cc; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Regulatory Document Analyzer</h1>
            
            <div class="status">
                <h3>✅ Service Status: Running</h3>
                <p>API is ready to analyze regulatory documents for SharePoint integration.</p>
                <p><strong>Timestamp:</strong> {{ timestamp }}</p>
            </div>

            <h2>Available Endpoints:</h2>
            
            <div class="endpoint">
                <h3><span class="method">POST</span> /analyze</h3>
                <p><strong>Purpose:</strong> Analyze a single regulatory document</p>
                <p><strong>Input:</strong> JSON with fileContent (base64) and fileName</p>
                <p><strong>Output:</strong> Structured analysis results</p>
            </div>

            <div class="endpoint">
                <h3><span class="method">POST</span> /batch-analyze</h3>
                <p><strong>Purpose:</strong> Analyze multiple documents at once</p>
                <p><strong>Input:</strong> JSON array of documents</p>
                <p><strong>Output:</strong> Batch analysis results</p>
            </div>

            <div class="endpoint">
                <h3><span class="method">GET</span> /health</h3>
                <p><strong>Purpose:</strong> Health check endpoint</p>
                <p><strong>Output:</strong> Service status</p>
            </div>

            <h2>SharePoint Integration Ready</h2>
            <p>This service is designed to work seamlessly with Power Automate flows from SharePoint. 
               Simply point your Power Automate HTTP action to <code>/analyze</code> endpoint.</p>
        </div>
    </body>
    </html>
    """, timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'))

@app.route('/analyze', methods=['POST'])
def analyze_document():
    """Main endpoint for document analysis"""
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        file_content_b64 = data.get('fileContent')
        file_name = data.get('fileName')
        
        if not file_content_b64 or not file_name:
            return jsonify({
                'success': False,
                'error': 'fileContent and fileName are required'
            }), 400
        
        # Decode base64 file content
        try:
            file_content = base64.b64decode(file_content_b64)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid base64 content: {str(e)}'
            }), 400
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_name).suffix) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # Extract text from document
            document_text = analyzer.parse_file(temp_file_path)
            
            if not document_text.strip():
                return jsonify({
                    'success': False,
                    'error': 'No text could be extracted from the document'
                }), 400
            
            # Analyze with AI
            analysis_result = analyzer.analyze_document(document_text)
            
            # Return success response
            return jsonify({
                'success': True,
                'analysis': analysis_result,
                'processedAt': datetime.now().isoformat(),
                'fileName': file_name,
                'documentLength': len(document_text)
            })
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error in analyze_document: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/batch-analyze', methods=['POST'])
def batch_analyze():
    """Batch analysis endpoint"""
    try:
        data = request.get_json()
        documents = data.get('documents', [])
        
        if not documents:
            return jsonify({
                'success': False,
                'error': 'No documents provided'
            }), 400
        
        results = []
        
        for doc in documents:
            try:
                file_content = base64.b64decode(doc['fileContent'])
                file_name = doc['fileName']
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_name).suffix) as temp_file:
                    temp_file.write(file_content)
                    temp_file_path = temp_file.name
                
                try:
                    # Process document
                    document_text = analyzer.parse_file(temp_file_path)
                    analysis_result = analyzer.analyze_document(document_text)
                    
                    results.append({
                        'success': True,
                        'fileName': file_name,
                        'analysis': analysis_result
                    })
                    
                finally:
                    os.unlink(temp_file_path)
                    
            except Exception as e:
                results.append({
                    'success': False,
                    'fileName': doc.get('fileName', 'unknown'),
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'totalDocuments': len(documents),
            'results': results,
            'processedAt': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in batch_analyze: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Regulatory Document Analyzer',
        'version': '1.0.0'
    })

@app.route('/test', methods=['GET', 'POST'])
def test_endpoint():
    """Test endpoint for quick verification"""
    if request.method == 'GET':
        return jsonify({
            'message': 'Test endpoint is working',
            'method': 'GET',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'message': 'Test endpoint received POST data',
            'data': request.get_json(),
            'timestamp': datetime.now().isoformat()
        })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint not found',
        'available_endpoints': ['/analyze', '/batch-analyze', '/health', '/test']
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal server error',
        'message': 'Something went wrong on the server'
    }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Regulatory Analyzer API on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)