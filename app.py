import streamlit as st
import json
import zipfile
import os
import tempfile
import base64
from io import BytesIO
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfWriter, PdfReader
import plotly.graph_objects as go
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="PDF Medical Form Filler",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants for data files in input folder
INPUT_FOLDER = os.path.join(os.path.dirname(__file__), "input") if os.path.exists(os.path.join(os.path.dirname(__file__), "input")) else "input"
PDF_FILE = "empty_form.pdf"
CASES_FILE = "cases_data.json"
FONT_FILE = "AzzamHandwriting-Regular.ttf"

# Initialize session state with FIXED field specs including signature
def initialize_session_state():
    if 'field_specs' not in st.session_state:
        st.session_state.field_specs = {
            "page1": {
                "date": {"x": 2.87, "y": 3.65, "w": 1.75, "h": 0.31, "font": 20},
                "age_gender": {"x": 2.87, "y": 3.04, "w": 3.21, "h": 0.25, "font": 16},
                "main_theme": {"x": 2.74, "y": 4.42, "w": 5.25, "h": 0.5, "font": 21},
                "case_summary": {"x": 0.34, "y": 5.25, "w": 7.70, "h": 1.04, "font": 18},
                "self_reflection_upper": {"x": 2.15, "y": 6.34, "w": 5.84, "h": 0.66, "font": 15},
                "self_reflection_lower": {"x": 4.00, "y": 7.12, "w": 4.00, "h": 1.17, "font": 15},
                "signature_mi": {"x": 1.0, "y": 9.5, "w": 3.0, "h": 0.5, "font": 14}
            },
            "page2": {
                "epa_row1": {"x": 0.62, "y": 3.30, "w": 1.5, "h": 0.45, "font": 32},
                "epa_row2": {"x": 0.62, "y": 3.35, "w": 1.5, "h": 0.45, "font": 32},
                "epa_row3": {"x": 0.62, "y": 4.18, "w": 1.5, "h": 0.45, "font": 32},
                "epa_row4": {"x": 0.62, "y": 4.68, "w": 1.5, "h": 0.45, "font": 32},
                "rubric_row1": {"x": 2.25, "y": 3.37, "w": 1.5, "h": 0.38, "font": 24},
                "rubric_row2": {"x": 2.25, "y": 3.87, "w": 1.5, "h": 0.38, "font": 24},
                "rubric_row3": {"x": 2.25, "y": 4.25, "w": 1.5, "h": 0.38, "font": 24},
                "rubric_row4": {"x": 2.25, "y": 4.75, "w": 1.5, "h": 0.38, "font": 24},
                "strength_row1": {"x": 3.87, "y": 3.37, "w": 1.63, "h": 0.38, "font": 16},
                "strength_row2": {"x": 3.87, "y": 3.87, "w": 1.63, "h": 0.38, "font": 16},
                "strength_row3": {"x": 3.87, "y": 4.30, "w": 1.63, "h": 0.38, "font": 16},
                "strength_row4": {"x": 3.87, "y": 4.76, "w": 1.63, "h": 0.38, "font": 16},
                "improve_row1": {"x": 5.50, "y": 3.37, "w": 1.62, "h": 0.38, "font": 16},
                "improve_row2": {"x": 5.50, "y": 3.83, "w": 1.62, "h": 0.38, "font": 16},
                "improve_row3": {"x": 5.50, "y": 4.29, "w": 1.62, "h": 0.38, "font": 16},
                "improve_row4": {"x": 5.50, "y": 4.75, "w": 1.62, "h": 0.38, "font": 16}
            }
        }

    # Initialize other session state variables
    for key, default in [
        ('pdf_images', {}),
        ('current_page', 1),
        ('selected_field', None),
        ('data_loaded', False),
        ('cases_data', []),
        ('pdf_bytes', None),
        ('font_bytes', None),
        ('loading_error', None)
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

@st.cache_data
def load_pdf_as_images(pdf_bytes):
    """Convert PDF to images for display"""
    images = {}
    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        dpi = 150
        
        for page_num in range(min(2, len(pdf_doc))):
            page = pdf_doc.load_page(page_num)
            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            img = Image.open(BytesIO(img_data))
            images[page_num + 1] = np.array(img)
        
        pdf_doc.close()
        return images
    except Exception as e:
        st.error(f"Error converting PDF to images: {str(e)}")
        return {}

def validate_case_data(case_data):
    """Validate that case data is a dictionary with expected structure"""
    if not isinstance(case_data, dict):
        return False, "Case data must be a dictionary/object"
    
    # Check for at least some expected fields
    expected_fields = ['case_id', 'date', 'age', 'gender', 'main_theme', 'case_summary']
    if not any(field in case_data for field in expected_fields):
        return False, f"Case data missing expected fields. Expected at least one of: {', '.join(expected_fields)}"
    
    return True, "Valid"

def load_input_data():
    """Load all required data from the input folder automatically"""
    
    # Check if input folder exists
    if not os.path.exists(INPUT_FOLDER):
        st.session_state.loading_error = f"❌ Input folder not found at: {INPUT_FOLDER}"
        return False
    
    errors = []
    
    # Load PDF file
    pdf_path = os.path.join(INPUT_FOLDER, PDF_FILE)
    if not os.path.exists(pdf_path):
        errors.append(f"• Missing: {PDF_FILE}")
    else:
        try:
            with open(pdf_path, 'rb') as f:
                st.session_state.pdf_bytes = f.read()
            st.session_state.pdf_images = load_pdf_as_images(st.session_state.pdf_bytes)
            if not st.session_state.pdf_images:
                errors.append(f"• Could not process: {PDF_FILE}")
        except Exception as e:
            errors.append(f"• Error loading {PDF_FILE}: {str(e)}")
    
    # Load cases data from cases_data.json with ROBUST ERROR HANDLING
    cases_path = os.path.join(INPUT_FOLDER, CASES_FILE)
    if not os.path.exists(cases_path):
        errors.append(f"• Missing: {CASES_FILE}")
    else:
        try:
            with open(cases_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            # CRITICAL FIX: Validate the loaded data structure
            if loaded_data is None:
                errors.append(f"• {CASES_FILE} is empty or null")
                st.session_state.cases_data = []
            elif isinstance(loaded_data, str):
                # Handle case where JSON might be double-encoded
                try:
                    loaded_data = json.loads(loaded_data)
                except:
                    errors.append(f"• {CASES_FILE} contains a string instead of JSON array")
                    st.session_state.cases_data = []
            
            # Ensure loaded_data is a list
            if isinstance(loaded_data, list):
                # Validate each case in the list
                valid_cases = []
                for i, case in enumerate(loaded_data):
                    if isinstance(case, dict):
                        valid_cases.append(case)
                    elif isinstance(case, str):
                        # Try to parse string as JSON
                        try:
                            parsed_case = json.loads(case)
                            if isinstance(parsed_case, dict):
                                valid_cases.append(parsed_case)
                            else:
                                errors.append(f"• Case {i+1} is not a valid object")
                        except:
                            errors.append(f"• Case {i+1} is a string but not valid JSON")
                    else:
                        errors.append(f"• Case {i+1} has invalid type: {type(case).__name__}")
                
                st.session_state.cases_data = valid_cases
                
                if len(valid_cases) < len(loaded_data):
                    errors.append(f"• Only {len(valid_cases)} of {len(loaded_data)} cases are valid")
                
                if not valid_cases:
                    errors.append(f"• No valid cases found in {CASES_FILE}")
            elif isinstance(loaded_data, dict):
                # Single case wrapped in object - convert to list
                st.session_state.cases_data = [loaded_data]
            else:
                errors.append(f"• {CASES_FILE} must contain a JSON array, got {type(loaded_data).__name__}")
                st.session_state.cases_data = []
                
        except json.JSONDecodeError as e:
            errors.append(f"• Invalid JSON in {CASES_FILE}: {str(e)}")
            st.session_state.cases_data = []
        except Exception as e:
            errors.append(f"• Error loading {CASES_FILE}: {str(e)}")
            st.session_state.cases_data = []
    
    # Load font (optional)
    font_path = os.path.join(INPUT_FOLDER, FONT_FILE)
    if os.path.exists(font_path):
        try:
            with open(font_path, 'rb') as f:
                st.session_state.font_bytes = f.read()
        except Exception as e:
            # Font is optional, so just warn
            pass
    
    # Check for errors
    if errors:
        st.session_state.loading_error = "❌ **Data Loading Errors:**\n\n" + "\n".join(errors)
        return False
    
    st.session_state.data_loaded = True
    st.session_state.loading_error = None
    return True

def inches_to_pixels(inches, dpi=150):
    return int(inches * dpi)

def pixels_to_inches(pixels, dpi=150):
    return pixels / dpi

def create_interactive_plotly_figure(page_num):
    """Create interactive Plotly figure with draggable rectangles"""
    if page_num not in st.session_state.pdf_images:
        return None
    
    # Get image
    img = st.session_state.pdf_images[page_num]
    img_height, img_width = img.shape[:2]
    
    # Convert image to base64 for Plotly
    img_pil = Image.fromarray(img)
    buffer = BytesIO()
    img_pil.save(buffer, format='PNG')
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # Create figure
    fig = go.Figure()
    
    # Add background image
    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{img_base64}",
            xref="x", yref="y",
            x=0, y=img_height,
            sizex=img_width, sizey=img_height,
            sizing="stretch",
            opacity=1.0,
            layer="below"
        )
    )
    
    # Add draggable shapes for each field
    page_key = f"page{page_num}"
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan',
              'magenta', 'yellow', 'lime', 'navy', 'teal', 'silver', 'maroon', 'fuchsia', 'aqua', 'black']
    
    for i, (field_name, spec) in enumerate(st.session_state.field_specs[page_key].items()):
        # Convert inches to pixels
        x_px = inches_to_pixels(spec['x'])
        y_px = img_height - inches_to_pixels(spec['y'] + spec['h'])  # Flip Y for Plotly
        w_px = inches_to_pixels(spec['w'])
        h_px = inches_to_pixels(spec['h'])
        
        color = colors[i % len(colors)]
        
        # Highlight selected field
        if field_name == st.session_state.selected_field:
            color = 'lime'
            opacity = 0.6
            line_width = 4
        else:
            opacity = 0.3
            line_width = 2
        
        # Add draggable rectangle
        fig.add_shape(
            type="rect",
            x0=x_px, y0=y_px,
            x1=x_px + w_px, y1=y_px + h_px,
            line=dict(color=color, width=line_width),
            fillcolor=color,
            opacity=opacity,
            editable=True,  # This makes it draggable
            name=field_name,
            layer="above"
        )
        
        # Add text annotation
        fig.add_annotation(
            x=x_px + w_px/2,
            y=y_px + h_px/2,
            text=field_name,
            showarrow=False,
            font=dict(size=10, color="white" if field_name == st.session_state.selected_field else "black"),
            bgcolor="black" if field_name == st.session_state.selected_field else "white",
            opacity=0.8,
            bordercolor="white",
            borderwidth=1
        )
    
    # Configure layout
    fig.update_layout(
        title=dict(
            text=f"🎯 Page {page_num} - Interactive Field Positioning<br>" +
                 f"<sub>Drag rectangles to reposition fields. Green = selected field.</sub>",
            x=0.5,
            font=dict(size=16)
        ),
        xaxis=dict(
            range=[0, img_width],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            fixedrange=False
        ),
        yaxis=dict(
            range=[0, img_height],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            scaleanchor="x",
            scaleratio=1,
            fixedrange=False
        ),
        width=900,
        height=1100,
        margin=dict(l=20, r=20, t=80, b=20),
        showlegend=False,
        dragmode='pan'
    )
    
    # Enable shape editing
    fig.update_shapes(dict(editable=True))
    
    return fig

def create_filled_pdf(case_data, pdf_bytes, font_bytes=None):
    """Create filled PDF for a single case with ROBUST ERROR HANDLING"""
    try:
        # CRITICAL FIX: Validate case_data is a dictionary
        if not isinstance(case_data, dict):
            st.error(f"Invalid case data type: {type(case_data).__name__}. Expected dictionary.")
            return None
            
        overlay_buffer = BytesIO()
        
        # Get original PDF dimensions
        original = PdfReader(BytesIO(pdf_bytes))
        first_page = original.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Create canvas
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
        
        # Setup font
        font_color = Color(0.102, 0.227, 0.486)  # #1A3A7C
        font_name = 'Helvetica'
        
        if font_bytes:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ttf') as tmp_font:
                    tmp_font.write(font_bytes)
                    tmp_font_path = tmp_font.name
                
                pdfmetrics.registerFont(TTFont('CustomFont', tmp_font_path))
                font_name = 'CustomFont'
                os.unlink(tmp_font_path)  # Clean up
            except:
                pass
        
        def draw_text(text, spec, page_height):
            if not text:
                return
            
            text = str(text).strip()
            if not text:
                return
            
            x_pts = spec['x'] * 72
            y_pts = (page_height/72 - spec['y'] - spec['h']/2) * 72
            w_pts = spec['w'] * 72
            
            c.setFont(font_name, spec['font'])
            c.setFillColor(font_color)
            
            # Handle long text with wrapping
            if len(text) > 50:
                words = text.split()
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = f"{current_line} {word}".strip()
                    text_width = c.stringWidth(test_line, font_name, spec['font'])
                    
                    if text_width <= w_pts - 10:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
                
                # Draw multiple lines
                line_height = spec['font'] + 2
                start_y = y_pts + (len(lines) - 1) * line_height / 2
                
                for line in lines:
                    line_width = c.stringWidth(line, font_name, spec['font'])
                    x_centered = x_pts + (w_pts - line_width) / 2
                    c.drawString(x_centered, start_y, line)
                    start_y -= line_height
            else:
                # Single line
                text_width = c.stringWidth(text, font_name, spec['font'])
                x_centered = x_pts + (w_pts - text_width) / 2
                c.drawString(x_centered, y_pts, text)
        
        # Fill Page 1 - INCLUDING SIGNATURE
        page1 = st.session_state.field_specs['page1']
        
        # SAFE GET with defaults to handle missing fields
        draw_text(case_data.get('date', ''), page1['date'], page_height)
        
        age_gender = f"{case_data.get('age', '')} {case_data.get('gender', '')}".strip()
        draw_text(age_gender, page1['age_gender'], page_height)
        
        draw_text(case_data.get('main_theme', ''), page1['main_theme'], page_height)
        draw_text(case_data.get('case_summary', ''), page1['case_summary'], page_height)
        
        # Handle self_reflection - check if it exists and is a dict
        reflection = case_data.get('self_reflection', {})
        if isinstance(reflection, dict):
            draw_text(reflection.get('what_did_right', ''), page1['self_reflection_upper'], page_height)
            draw_text(reflection.get('needs_development', ''), page1['self_reflection_lower'], page_height)
        
        # SIGNATURE FIELD - FIXED
        draw_text(case_data.get('signature_mi', ''), page1['signature_mi'], page_height)
        
        # Page 2
        c.showPage()
        page2 = st.session_state.field_specs['page2']
        
        # Handle EPA assessment - check if it exists and is a dict
        epa_data = case_data.get('epa_assessment', {})
        if isinstance(epa_data, dict):
            # Fill EPA table with safe defaults
            epas = epa_data.get('epa_tested', ['EPA 2', 'EPA 6', 'EPA 9', 'EPA 12'])
            rubrics = epa_data.get('rubric_levels', ['Level C'] * 4)
            strengths = epa_data.get('strength_points', ['Good work'] * 4)
            improvements = epa_data.get('points_needing_improvement', ['Keep practicing'] * 4)
            
            # Ensure lists are lists
            epas = epas if isinstance(epas, list) else []
            rubrics = rubrics if isinstance(rubrics, list) else []
            strengths = strengths if isinstance(strengths, list) else []
            improvements = improvements if isinstance(improvements, list) else []
            
            for i in range(4):
                row = i + 1
                if i < len(epas):
                    draw_text(epas[i], page2[f'epa_row{row}'], page_height)
                if i < len(rubrics):
                    draw_text(rubrics[i], page2[f'rubric_row{row}'], page_height)
                if i < len(strengths):
                    draw_text(strengths[i], page2[f'strength_row{row}'], page_height)
                if i < len(improvements):
                    draw_text(improvements[i], page2[f'improve_row{row}'], page_height)
        
        c.save()
        overlay_buffer.seek(0)
        
        # Merge with original PDF
        original_pdf = PdfReader(BytesIO(pdf_bytes))
        overlay_pdf = PdfReader(overlay_buffer)
        writer = PdfWriter()
        
        for page_num in range(len(original_pdf.pages)):
            page = original_pdf.pages[page_num]
            if page_num < len(overlay_pdf.pages):
                overlay_page = overlay_pdf.pages[page_num]
                page.merge_page(overlay_page)
            writer.add_page(page)
        
        # Return PDF bytes
        output_buffer = BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        return output_buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error creating PDF for case: {str(e)}")
        return None

def main():
    """Main application"""
    
    # Initialize session state FIRST
    initialize_session_state()
    
    # Auto-load data on startup
    if not st.session_state.data_loaded and not st.session_state.loading_error:
        with st.spinner("🔄 Loading data from /input folder..."):
            load_input_data()
    
    # Show header
    st.title("📋 PDF Medical Form Filler")
    st.markdown("*Interactive field positioning with drag-and-drop functionality*")
    
    # Handle loading errors
    if st.session_state.loading_error:
        st.error(st.session_state.loading_error)
        
        with st.expander("📁 **Setup Instructions**", expanded=True):
            st.markdown(f"""
            **Required files in `/input` folder:**
            
            ```
            {INPUT_FOLDER}/
            ├── {PDF_FILE}          # Your blank PDF form template
            ├── {CASES_FILE}         # Your case data in JSON format
            └── {FONT_FILE}  # Custom font (optional)
            ```
            
            **JSON Format Required:**
            Your `{CASES_FILE}` must be a JSON array of objects:
            ```json
            [
              {{
                "case_id": "case_001",
                "date": "2024-01-15",
                "age": "28",
                "gender": "Male",
                "main_theme": "...",
                "case_summary": "...",
                "self_reflection": {{
                  "what_did_right": "...",
                  "needs_development": "..."
                }},
                "signature_mi": "Dr. Smith",
                "epa_assessment": {{
                  "epa_tested": ["EPA 1", "EPA 2", ...],
                  "rubric_levels": ["Level A", "Level B", ...],
                  "strength_points": ["...", ...],
                  "points_needing_improvement": ["...", ...]
                }}
              }},
              ...
            ]
            ```
            
            **Troubleshooting:**
            - Ensure the `/input` folder exists in your repository
            - Check that filenames match exactly (case-sensitive)
            - Verify file formats: PDF, JSON, TTF/OTF
            - Make sure files are not corrupted
            - Validate JSON syntax at jsonlint.com
            
            **Current input folder location:** `{INPUT_FOLDER}`
            """)
        
        if st.button("🔄 Retry Loading Data"):
            st.session_state.data_loaded = False
            st.session_state.loading_error = None
            st.session_state.cases_data = []  # Reset to empty list
            st.rerun()
        
        return
    
    # Show data status in sidebar
    st.sidebar.header("📁 Loaded Data")
    st.sidebar.success(f"✅ PDF Template: {PDF_FILE}")
    
    # SAFE handling of cases count
    cases_count = len(st.session_state.cases_data) if isinstance(st.session_state.cases_data, list) else 0
    st.sidebar.success(f"✅ Cases: {cases_count} loaded")
    
    if st.session_state.font_bytes:
        st.sidebar.success(f"✅ Custom Font: {FONT_FILE}")
    else:
        st.sidebar.info(f"ℹ️ Using default font (no {FONT_FILE} found)")
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"📂 Data source: `/input` folder")
    
    # Main interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("🎯 Interactive Field Positioning")
        
        # Page and field selection with FIXED session state handling
        col_page, col_field = st.columns([1, 2])
        
        with col_page:
            page_option = st.selectbox("📄 Select Page", ["Page 1", "Page 2"])
            current_page = 1 if page_option == "Page 1" else 2
            st.session_state.current_page = current_page
        
        with col_field:
            page_key = f"page{current_page}"
            field_names = list(st.session_state.field_specs[page_key].keys())
            
            # FIXED: Ensure selected field is valid for current page
            if (st.session_state.selected_field is None or 
                st.session_state.selected_field not in field_names):
                st.session_state.selected_field = field_names[0] if field_names else None
            
            if field_names:
                current_index = field_names.index(st.session_state.selected_field) if st.session_state.selected_field in field_names else 0
                selected_field = st.selectbox("🎯 Select Field", field_names, 
                                            index=current_index,
                                            key=f"field_selector_{current_page}")
                st.session_state.selected_field = selected_field
        
        # Create and display interactive Plotly figure
        if current_page in st.session_state.pdf_images:
            fig = create_interactive_plotly_figure(current_page)
            
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"plotly_fig_{current_page}")
                
                st.info("💡 **Tip:** Drag the colored rectangles directly on the PDF to reposition fields. Green = selected field.")
        
        # FIXED: Precise adjustment controls with proper session state preservation
        st.subheader(f"📐 Fine-tune '{st.session_state.selected_field}' Position")
        
        if st.session_state.selected_field:
            page_key = f"page{current_page}"
            spec = st.session_state.field_specs[page_key][st.session_state.selected_field]
            
            # FIXED: Use unique keys that persist across page switches
            field_key = f"{page_key}_{st.session_state.selected_field}"
            
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.slider("X Position (inches)", 0.0, 8.5, value=float(spec['x']), step=0.05, 
                                key=f"x_{field_key}")
            with col_y:
                new_y = st.slider("Y Position (inches)", 0.0, 11.0, value=float(spec['y']), step=0.05,
                                key=f"y_{field_key}")
            
            col_w, col_h = st.columns(2)
            with col_w:
                new_w = st.slider("Width (inches)", 0.1, 8.0, value=float(spec['w']), step=0.05,
                                key=f"w_{field_key}")
            with col_h:
                new_h = st.slider("Height (inches)", 0.1, 3.0, value=float(spec['h']), step=0.05,
                                key=f"h_{field_key}")
            
            # FIXED: Update field specs immediately to preserve changes
            st.session_state.field_specs[page_key][st.session_state.selected_field]['x'] = round(new_x, 2)
            st.session_state.field_specs[page_key][st.session_state.selected_field]['y'] = round(new_y, 2)
            st.session_state.field_specs[page_key][st.session_state.selected_field]['w'] = round(new_w, 2)
            st.session_state.field_specs[page_key][st.session_state.selected_field]['h'] = round(new_h, 2)
            
            # Show current values
            st.success(f"📍 **{st.session_state.selected_field}**: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\"")
    
    with col2:
        st.header("🎛️ Controls")
        
        # Coordinate display
        if st.button("📊 Show All Coordinates", use_container_width=True):
            st.subheader("Current Coordinates")
            for page_key, fields in st.session_state.field_specs.items():
                st.write(f"**{page_key.upper()}:**")
                coord_data = []
                for field_name, spec in fields.items():
                    coord_data.append({
                        'Field': field_name.replace('_', ' ').title(),
                        'X': f"{spec['x']:.2f}\"",
                        'Y': f"{spec['y']:.2f}\"", 
                        'W': f"{spec['w']:.2f}\"",
                        'H': f"{spec['h']:.2f}\"",
                        'Font': f"{spec['font']}pt"
                    })
                st.dataframe(coord_data, use_container_width=True)
        
        st.markdown("---")
        
        # FIXED: Form processing with ROBUST error handling
        st.subheader("📄 Process Forms")
        
        # SAFE cases count
        st.write(f"**📊 Cases to process:** {cases_count}")
        
        if cases_count == 0:
            st.warning("No valid cases found in cases_data.json")
            st.info("💡 Make sure your cases_data.json file contains a valid JSON array of case objects.")
        else:
            # Show sample case structure for verification - FIXED WITH SAFETY CHECKS
            if st.button("👁️ Preview First Case", use_container_width=True):
                try:
                    if (isinstance(st.session_state.cases_data, list) and 
                        len(st.session_state.cases_data) > 0):
                        first_case = st.session_state.cases_data[0]
                        if isinstance(first_case, dict):
                            st.json(first_case)
                        else:
                            st.error(f"First case is not a valid object. Type: {type(first_case).__name__}")
                    else:
                        st.warning("No cases available to preview")
                except Exception as e:
                    st.error(f"Error previewing case: {str(e)}")
            
            if st.button("🚀 Fill All Forms", type="primary", use_container_width=True):
                
                # FIXED: Proper progress tracking with correct placeholder methods
                progress_bar = st.progress(0)
                status_container = st.container()
                
                filled_pdfs = {}
                failed_cases = []
                
                try:
                    for i, case in enumerate(st.session_state.cases_data):
                        # VALIDATE each case is a dictionary
                        if not isinstance(case, dict):
                            failed_cases.append(f"Case {i+1}: Invalid type ({type(case).__name__})")
                            continue
                        
                        # FIXED: Use container with text() method
                        with status_container:
                            case_id = case.get('case_id', f'Case {i+1}')
                            st.text(f"Processing case {i+1}/{cases_count}: {case_id}")
                        
                        progress_bar.progress((i + 1) / cases_count)
                        
                        # Process the case
                        try:
                            filled_pdf = create_filled_pdf(case, st.session_state.pdf_bytes, st.session_state.font_bytes)
                            
                            if filled_pdf:
                                filled_pdfs[f"{case_id}_filled.pdf"] = filled_pdf
                            else:
                                failed_cases.append(f"{case_id}: PDF creation failed")
                        except Exception as e:
                            failed_cases.append(f"{case_id}: {str(e)}")
                    
                    # Create ZIP file if we have any successful PDFs
                    if filled_pdfs:
                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for filename, pdf_data in filled_pdfs.items():
                                zip_file.writestr(filename, pdf_data)
                        
                        zip_buffer.seek(0)
                        
                        # FIXED: Clear status and show success
                        status_container.empty()
                        progress_bar.empty()
                        
                        if failed_cases:
                            st.warning(f"⚠️ Processed {len(filled_pdfs)} of {cases_count} forms successfully")
                            with st.expander("Failed Cases"):
                                for error in failed_cases:
                                    st.error(error)
                        else:
                            st.success(f"🎉 Successfully processed all {len(filled_pdfs)} forms!")
                            st.balloons()
                        
                        st.download_button(
                            label=f"📥 Download {len(filled_pdfs)} Filled Forms (ZIP)",
                            data=zip_buffer.getvalue(),
                            file_name="filled_medical_forms.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                    else:
                        status_container.empty()
                        progress_bar.empty()
                        st.error("❌ No forms were successfully processed")
                        if failed_cases:
                            with st.expander("Error Details"):
                                for error in failed_cases:
                                    st.error(error)
                
                except Exception as e:
                    status_container.empty()
                    progress_bar.empty()
                    st.error(f"❌ Critical error during processing: {str(e)}")
                    st.exception(e)
        
        # Instructions
        st.markdown("---")
        st.subheader("📋 How to Use")
        st.markdown("""
        **🎯 Positioning:**
        1. Select page and field
        2. Drag rectangles on PDF
        3. Fine-tune with sliders
        4. Green = selected field
        
        **📄 Processing:**
        1. Position all fields correctly
        2. Click "Fill All Forms"  
        3. Download ZIP file
        
        **💡 Tips:**
        - Positions are saved automatically
        - Switch pages without losing changes
        - Data loads from input/cases_data.json
        """)

if __name__ == "__main__":
    main()
