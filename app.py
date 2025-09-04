import streamlit as st
import json
import zipfile
import os
import tempfile
import base64
import re
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
import copy
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

# Default field specifications
DEFAULT_SPECS = {
    "page1": {
        "date": {"x": 1.5, "y": 2.6, "w": 2.5, "h": 0.25, "font": 20},
        "age_gender": {"x": 2.2, "y": 3.0, "w": 3.0, "h": 0.25, "font": 16.1},
        "main_theme": {"x": 1.2, "y": 3.6, "w": 6.5, "h": 0.4, "font": 21},
        "case_summary": {"x": 0.8, "y": 4.3, "w": 7.0, "h": 1.5, "font": 18},
        "self_reflection_upper": {"x": 0.8, "y": 6.2, "w": 7.0, "h": 0.6, "font": 15},
        "self_reflection_lower": {"x": 0.8, "y": 7.0, "w": 7.0, "h": 1.0, "font": 15},
        "signature_mi": {"x": 0.8, "y": 9.8, "w": 3.0, "h": 0.3, "font": 24}
    },
    "page2": {
        "epa_row1": {"x": 0.6, "y": 1.8, "w": 1.8, "h": 0.35, "font": 14},
        "epa_row2": {"x": 0.6, "y": 2.4, "w": 1.8, "h": 0.35, "font": 14},
        "epa_row3": {"x": 0.6, "y": 3.0, "w": 1.8, "h": 0.35, "font": 14},
        "epa_row4": {"x": 0.6, "y": 3.6, "w": 1.8, "h": 0.35, "font": 14},
        "rubric_row1": {"x": 2.5, "y": 1.8, "w": 1.5, "h": 0.35, "font": 14},
        "rubric_row2": {"x": 2.5, "y": 2.4, "w": 1.5, "h": 0.35, "font": 14},
        "rubric_row3": {"x": 2.5, "y": 3.0, "w": 1.5, "h": 0.35, "font": 14},
        "rubric_row4": {"x": 2.5, "y": 3.6, "w": 1.5, "h": 0.35, "font": 14},
        "strength_row1": {"x": 4.1, "y": 1.8, "w": 1.8, "h": 0.35, "font": 12},
        "strength_row2": {"x": 4.1, "y": 2.4, "w": 1.8, "h": 0.35, "font": 12},
        "strength_row3": {"x": 4.1, "y": 3.0, "w": 1.8, "h": 0.35, "font": 12},
        "strength_row4": {"x": 4.1, "y": 3.6, "w": 1.8, "h": 0.35, "font": 12},
        "improve_row1": {"x": 6.0, "y": 1.8, "w": 1.8, "h": 0.35, "font": 12},
        "improve_row2": {"x": 6.0, "y": 2.4, "w": 1.8, "h": 0.35, "font": 12},
        "improve_row3": {"x": 6.0, "y": 3.0, "w": 1.8, "h": 0.35, "font": 12},
        "improve_row4": {"x": 6.0, "y": 3.6, "w": 1.8, "h": 0.35, "font": 12}
    }
}

def initialize_session_state():
    """Initialize session state with proper separation of saved and draft states"""
    
    # SAVED positions - these are the committed positions used for PDF generation
    if 'saved_positions' not in st.session_state:
        st.session_state.saved_positions = copy.deepcopy(DEFAULT_SPECS)
    
    # DRAFT positions - these are the working positions being edited
    if 'draft_positions' not in st.session_state:
        st.session_state.draft_positions = copy.deepcopy(st.session_state.saved_positions)
    
    # Track unsaved changes per page
    if 'unsaved_changes' not in st.session_state:
        st.session_state.unsaved_changes = {"page1": False, "page2": False}
    
    # Initialize other session state variables
    for key, default in [
        ('pdf_images', {}),
        ('current_page', 1),
        ('selected_field', None),
        ('data_loaded', False),
        ('cases_data', []),
        ('pdf_bytes', None),
        ('font_bytes', None),
        ('loading_error', None),
        ('positions_modified', False),  # Track if positions differ from defaults
        ('show_save_confirmation', {"page1": False, "page2": False})
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

def check_if_modified():
    """Check if saved positions differ from defaults"""
    for page_key in ['page1', 'page2']:
        for field_name, spec in st.session_state.saved_positions[page_key].items():
            default_spec = DEFAULT_SPECS[page_key][field_name]
            if (abs(spec['x'] - default_spec['x']) > 0.01 or 
                abs(spec['y'] - default_spec['y']) > 0.01 or
                abs(spec['w'] - default_spec['w']) > 0.01 or
                abs(spec['h'] - default_spec['h']) > 0.01):
                return True
    return False

def save_current_page_positions(page_num):
    """Save draft positions for the current page to saved positions"""
    page_key = f"page{page_num}"
    st.session_state.saved_positions[page_key] = copy.deepcopy(st.session_state.draft_positions[page_key])
    st.session_state.unsaved_changes[page_key] = False
    st.session_state.show_save_confirmation[page_key] = True
    st.session_state.positions_modified = check_if_modified()

def reset_all_positions():
    """Reset all positions to defaults"""
    st.session_state.saved_positions = copy.deepcopy(DEFAULT_SPECS)
    st.session_state.draft_positions = copy.deepcopy(DEFAULT_SPECS)
    st.session_state.unsaved_changes = {"page1": False, "page2": False}
    st.session_state.positions_modified = False

def update_draft_position(page_key, field_name, coord_type, value):
    """Update draft position and mark as having unsaved changes"""
    st.session_state.draft_positions[page_key][field_name][coord_type] = value
    st.session_state.unsaved_changes[page_key] = True

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

def transform_case_format(original_case):
    """Transform case from user's format to expected format"""
    transformed = {}
    
    # Map Date -> date
    if 'Date' in original_case:
        transformed['date'] = original_case['Date']
    
    # Parse "Age & Gender" into combined field
    if 'Age & Gender' in original_case:
        transformed['age_gender'] = original_case['Age & Gender']
        
        # Also extract separate fields for compatibility
        age_gender = original_case['Age & Gender']
        age_match = re.search(r'(\d+)', age_gender)
        if age_match:
            transformed['age'] = age_match.group(1)
        
        gender_lower = age_gender.lower()
        if 'male' in gender_lower and 'female' not in gender_lower:
            transformed['gender'] = 'Male'
        elif 'female' in gender_lower:
            transformed['gender'] = 'Female'
        elif 'non-binary' in gender_lower or 'nonbinary' in gender_lower:
            transformed['gender'] = 'Non-binary'
        else:
            transformed['gender'] = ''
    
    # Map field names
    field_mappings = {
        'Main theme of the case': 'main_theme',
        'Case Summary': 'case_summary',
        'Signature of the MI': 'signature_mi'
    }
    
    for old_key, new_key in field_mappings.items():
        if old_key in original_case:
            transformed[new_key] = original_case[old_key]
    
    # Handle Self Reflection
    if 'Self Reflection' in original_case:
        reflection_text = original_case['Self Reflection']
        transformed['self_reflection'] = {}
        
        if 'Did well:' in reflection_text:
            parts = reflection_text.split('Needs work:')
            if len(parts) >= 1:
                did_well = parts[0].replace('Did well:', '').strip()
                if 'Plan:' in did_well:
                    did_well = did_well.split('Plan:')[0].strip()
                transformed['self_reflection']['what_did_right'] = did_well
            
            if len(parts) >= 2:
                needs_work = parts[1].strip()
                transformed['self_reflection']['needs_development'] = needs_work
        else:
            transformed['self_reflection']['what_did_right'] = reflection_text
            transformed['self_reflection']['needs_development'] = ''
    
    # Handle EPA assessment
    transformed['epa_assessment'] = {}
    
    if 'EPA tested' in original_case:
        epas = original_case['EPA tested']
        if isinstance(epas, list):
            transformed['epa_assessment']['epa_tested'] = [f"EPA {epa}" if isinstance(epa, (int, float)) else str(epa) for epa in epas]
        else:
            transformed['epa_assessment']['epa_tested'] = []
    
    if 'Rubric' in original_case:
        transformed['epa_assessment']['rubric_levels'] = original_case['Rubric'] if isinstance(original_case['Rubric'], list) else []
    
    if 'Strength points' in original_case:
        transformed['epa_assessment']['strength_points'] = original_case['Strength points'] if isinstance(original_case['Strength points'], list) else []
    
    if 'Points needing improvement' in original_case:
        transformed['epa_assessment']['points_needing_improvement'] = original_case['Points needing improvement'] if isinstance(original_case['Points needing improvement'], list) else []
    
    # Generate a case_id if not present
    if 'case_id' not in transformed:
        date_part = transformed.get('date', '').replace('-', '')
        theme_part = transformed.get('main_theme', 'case')[:20].replace(' ', '_').replace('/', '_')
        transformed['case_id'] = f"case_{date_part}_{theme_part}" if date_part else f"case_{theme_part}"
    
    return transformed

def load_input_data():
    """Load all required data from the input folder automatically"""
    
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
    
    # Load cases data
    cases_path = os.path.join(INPUT_FOLDER, CASES_FILE)
    if not os.path.exists(cases_path):
        errors.append(f"• Missing: {CASES_FILE}")
    else:
        try:
            with open(cases_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            # Handle object with "cases" array
            if isinstance(loaded_data, dict) and 'cases' in loaded_data:
                cases_array = loaded_data['cases']
                if isinstance(cases_array, list):
                    valid_cases = []
                    for i, case in enumerate(cases_array):
                        if isinstance(case, dict):
                            try:
                                transformed_case = transform_case_format(case)
                                valid_cases.append(transformed_case)
                            except Exception as e:
                                errors.append(f"• Case {i+1} transformation error: {str(e)}")
                    st.session_state.cases_data = valid_cases
                else:
                    errors.append(f"• 'cases' property is not an array")
                    st.session_state.cases_data = []
            
            # Handle direct array format
            elif isinstance(loaded_data, list):
                valid_cases = []
                for i, case in enumerate(loaded_data):
                    if isinstance(case, dict):
                        if 'Date' in case or 'Age & Gender' in case:
                            try:
                                transformed_case = transform_case_format(case)
                                valid_cases.append(transformed_case)
                            except Exception as e:
                                errors.append(f"• Case {i+1} transformation error: {str(e)}")
                        else:
                            valid_cases.append(case)
                st.session_state.cases_data = valid_cases
            else:
                errors.append(f"• {CASES_FILE} must contain JSON array or object with 'cases' array")
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
        except:
            pass
    
    if errors:
        st.session_state.loading_error = "❌ **Data Loading Errors:**\n\n" + "\n".join(errors)
        return False
    
    st.session_state.data_loaded = True
    st.session_state.loading_error = None
    return True

def inches_to_pixels(inches, dpi=150):
    return int(inches * dpi)

def create_interactive_plotly_figure(page_num):
    """Create interactive Plotly figure with draggable rectangles"""
    if page_num not in st.session_state.pdf_images:
        return None
    
    img = st.session_state.pdf_images[page_num]
    img_height, img_width = img.shape[:2]
    
    img_pil = Image.fromarray(img)
    buffer = BytesIO()
    img_pil.save(buffer, format='PNG')
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    fig = go.Figure()
    
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
    
    page_key = f"page{page_num}"
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan',
              'magenta', 'yellow', 'lime', 'navy', 'teal', 'silver', 'maroon', 'fuchsia', 'aqua', 'black']
    
    # Use DRAFT positions for display
    for i, (field_name, spec) in enumerate(st.session_state.draft_positions[page_key].items()):
        x_px = inches_to_pixels(spec['x'])
        y_px = img_height - inches_to_pixels(spec['y'] + spec['h'])
        w_px = inches_to_pixels(spec['w'])
        h_px = inches_to_pixels(spec['h'])
        
        color = colors[i % len(colors)]
        
        if field_name == st.session_state.selected_field:
            color = 'lime'
            opacity = 0.6
            line_width = 4
        else:
            opacity = 0.3
            line_width = 2
        
        fig.add_shape(
            type="rect",
            x0=x_px, y0=y_px,
            x1=x_px + w_px, y1=y_px + h_px,
            line=dict(color=color, width=line_width),
            fillcolor=color,
            opacity=opacity,
            editable=True,
            name=field_name,
            layer="above"
        )
        
        # Show font size in annotation
        font_size = spec['font']
        fig.add_annotation(
            x=x_px + w_px/2,
            y=y_px + h_px/2,
            text=f"{field_name}<br>Font: {font_size}pt",
            showarrow=False,
            font=dict(size=10, color="white" if field_name == st.session_state.selected_field else "black"),
            bgcolor="black" if field_name == st.session_state.selected_field else "white",
            opacity=0.8,
            bordercolor="white",
            borderwidth=1
        )
    
    # Add indicator for unsaved changes
    title_suffix = " (UNSAVED CHANGES)" if st.session_state.unsaved_changes[page_key] else ""
    
    fig.update_layout(
        title=dict(
            text=f"🎯 Page {page_num} - Interactive Field Positioning{title_suffix}<br>" +
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
    
    fig.update_shapes(dict(editable=True))
    
    return fig

def create_filled_pdf(case_data, pdf_bytes, font_bytes=None):
    """Create filled PDF using SAVED positions (not draft)"""
    try:
        if not isinstance(case_data, dict):
            st.error(f"Invalid case data type: {type(case_data).__name__}")
            return None
            
        overlay_buffer = BytesIO()
        
        original = PdfReader(BytesIO(pdf_bytes))
        first_page = original.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
        
        # Setup font
        font_color = Color(0.102, 0.227, 0.486)  # Blue color
        font_name = 'Helvetica'
        
        if font_bytes:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ttf') as tmp_font:
                    tmp_font.write(font_bytes)
                    tmp_font_path = tmp_font.name
                
                pdfmetrics.registerFont(TTFont('CustomFont', tmp_font_path))
                font_name = 'CustomFont'
                os.unlink(tmp_font_path)
            except:
                pass
        
        def draw_text(text, spec, page_height):
            """Draw text using saved positions and font sizes"""
            if not text:
                return
            
            text = str(text).strip()
            if not text:
                return
            
            # Use positions from spec (which comes from saved_positions)
            x_pts = spec['x'] * 72
            y_pts = (page_height/72 - spec['y'] - spec['h']/2) * 72
            w_pts = spec['w'] * 72
            
            # Use the font size from the spec
            font_size = spec['font']
            c.setFont(font_name, font_size)
            c.setFillColor(font_color)
            
            # Handle long text with wrapping
            if len(text) > 50 and spec['h'] > 0.5:
                words = text.split()
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = f"{current_line} {word}".strip()
                    text_width = c.stringWidth(test_line, font_name, font_size)
                    
                    if text_width <= w_pts - 10:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
                
                # Draw multiple lines
                line_height = font_size + 2
                start_y = y_pts + (len(lines) - 1) * line_height / 2
                
                for line in lines:
                    c.drawString(x_pts + 5, start_y, line)
                    start_y -= line_height
            else:
                # Single line
                c.drawString(x_pts + 5, y_pts, text)
        
        # CRITICAL: Always use saved_positions for PDF generation
        saved_specs = st.session_state.saved_positions
        
        # FILL PAGE 1
        page1_specs = saved_specs['page1']
        
        draw_text(case_data.get('date', ''), page1_specs['date'], page_height)
        
        # Age & Gender
        if 'age_gender' in case_data:
            draw_text(case_data['age_gender'], page1_specs['age_gender'], page_height)
        else:
            age_gender = f"{case_data.get('age', '')} {case_data.get('gender', '')}".strip()
            draw_text(age_gender, page1_specs['age_gender'], page_height)
        
        draw_text(case_data.get('main_theme', ''), page1_specs['main_theme'], page_height)
        draw_text(case_data.get('case_summary', ''), page1_specs['case_summary'], page_height)
        
        # Self Reflection
        reflection = case_data.get('self_reflection', {})
        if isinstance(reflection, dict):
            draw_text(reflection.get('what_did_right', ''), page1_specs['self_reflection_upper'], page_height)
            draw_text(reflection.get('needs_development', ''), page1_specs['self_reflection_lower'], page_height)
        
        draw_text(case_data.get('signature_mi', ''), page1_specs['signature_mi'], page_height)
        
        # PAGE 2
        c.showPage()
        page2_specs = saved_specs['page2']
        epa_data = case_data.get('epa_assessment', {})
        
        if isinstance(epa_data, dict):
            epas = epa_data.get('epa_tested', [])
            rubrics = epa_data.get('rubric_levels', [])
            strengths = epa_data.get('strength_points', [])
            improvements = epa_data.get('points_needing_improvement', [])
            
            # Ensure all are lists
            epas = epas if isinstance(epas, list) else []
            rubrics = rubrics if isinstance(rubrics, list) else []
            strengths = strengths if isinstance(strengths, list) else []
            improvements = improvements if isinstance(improvements, list) else []
            
            # Fill table
            for i in range(min(4, max(len(epas), len(rubrics), len(strengths), len(improvements)))):
                row_num = i + 1
                
                if i < len(epas):
                    draw_text(str(epas[i]), page2_specs[f'epa_row{row_num}'], page_height)
                
                if i < len(rubrics):
                    draw_text(str(rubrics[i]), page2_specs[f'rubric_row{row_num}'], page_height)
                
                if i < len(strengths):
                    draw_text(str(strengths[i]), page2_specs[f'strength_row{row_num}'], page_height)
                
                if i < len(improvements):
                    draw_text(str(improvements[i]), page2_specs[f'improve_row{row_num}'], page_height)
        
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
        
        output_buffer = BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        return output_buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error creating PDF: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

def main():
    """Main application"""
    
    initialize_session_state()
    
    if not st.session_state.data_loaded and not st.session_state.loading_error:
        with st.spinner("🔄 Loading data from /input folder..."):
            load_input_data()
    
    st.title("📋 PDF Medical Form Filler")
    st.markdown("*Interactive field positioning with custom font sizes*")
    
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
            """)
        
        if st.button("🔄 Retry Loading Data"):
            st.session_state.data_loaded = False
            st.session_state.loading_error = None
            st.session_state.cases_data = []
            st.rerun()
        
        return
    
    # Show data status
    st.sidebar.header("📁 Loaded Data")
    st.sidebar.success(f"✅ PDF Template: {PDF_FILE}")
    
    cases_count = len(st.session_state.cases_data) if isinstance(st.session_state.cases_data, list) else 0
    st.sidebar.success(f"✅ Cases: {cases_count} loaded")
    
    if st.session_state.font_bytes:
        st.sidebar.success(f"✅ Custom Font: {FONT_FILE}")
    else:
        st.sidebar.info(f"ℹ️ Using default font")
    
    st.sidebar.markdown("---")
    
    # Position Status
    st.sidebar.header("📍 Position Status")
    
    # Check for unsaved changes
    has_unsaved = st.session_state.unsaved_changes["page1"] or st.session_state.unsaved_changes["page2"]
    
    if has_unsaved:
        st.sidebar.error("❗ You have unsaved changes!")
        if st.session_state.unsaved_changes["page1"]:
            st.sidebar.warning("• Page 1 has unsaved changes")
        if st.session_state.unsaved_changes["page2"]:
            st.sidebar.warning("• Page 2 has unsaved changes")
    else:
        st.sidebar.success("✅ All changes saved")
    
    if st.session_state.positions_modified:
        st.sidebar.info("📝 Positions modified from defaults")
    
    # Reset button
    if st.sidebar.button("🔄 Reset ALL to Default Positions", use_container_width=True):
        reset_all_positions()
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Show loaded cases summary
    if cases_count > 0:
        st.sidebar.subheader("📊 Cases Summary")
        for i, case in enumerate(st.session_state.cases_data[:5]):
            case_id = case.get('case_id', f'Case {i+1}')
            date = case.get('date', 'No date')
            st.sidebar.text(f"{i+1}. {date}")
        if cases_count > 5:
            st.sidebar.text(f"... and {cases_count - 5} more")
    
    # Main interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("🎯 Interactive Field Positioning")
        
        # Show save confirmation messages
        if st.session_state.show_save_confirmation["page1"]:
            st.success("✅ Page 1 positions saved successfully!")
            st.session_state.show_save_confirmation["page1"] = False
            
        if st.session_state.show_save_confirmation["page2"]:
            st.success("✅ Page 2 positions saved successfully!")
            st.session_state.show_save_confirmation["page2"] = False
        
        col_page, col_field = st.columns([1, 2])
        
        with col_page:
            page_option = st.selectbox("📄 Select Page", ["Page 1", "Page 2"])
            current_page = 1 if page_option == "Page 1" else 2
            st.session_state.current_page = current_page
        
        with col_field:
            page_key = f"page{current_page}"
            field_names = list(st.session_state.draft_positions[page_key].keys())
            
            if (st.session_state.selected_field is None or 
                st.session_state.selected_field not in field_names):
                st.session_state.selected_field = field_names[0] if field_names else None
            
            if field_names:
                current_index = field_names.index(st.session_state.selected_field) if st.session_state.selected_field in field_names else 0
                selected_field = st.selectbox("🎯 Select Field", field_names, 
                                            index=current_index,
                                            key=f"field_selector_{current_page}")
                st.session_state.selected_field = selected_field
        
        # SAVE BUTTON for current page
        col_save, col_status = st.columns([1, 2])
        with col_save:
            page_key = f"page{current_page}"
            if st.session_state.unsaved_changes[page_key]:
                if st.button(f"💾 **SAVE Page {current_page} Positions**", 
                           type="primary", 
                           use_container_width=True,
                           help="Save all position changes for this page"):
                    save_current_page_positions(current_page)
                    st.rerun()
            else:
                st.button(f"✅ Page {current_page} Saved", 
                         use_container_width=True, 
                         disabled=True,
                         help="No changes to save")
        
        with col_status:
            if st.session_state.unsaved_changes[page_key]:
                st.warning(f"⚠️ Page {current_page} has unsaved changes. Click SAVE to apply them to PDFs.")
            else:
                st.info(f"✅ Page {current_page} positions are saved and will be used for PDF generation.")
        
        if current_page in st.session_state.pdf_images:
            fig = create_interactive_plotly_figure(current_page)
            
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"plotly_fig_{current_page}")
                
                st.info("💡 **Tip:** Adjust positions with sliders below. Remember to SAVE before switching pages or generating PDFs!")
        
        # Field adjustment controls
        st.subheader(f"📐 Fine-tune '{st.session_state.selected_field}' Position")
        
        if st.session_state.selected_field:
            page_key = f"page{current_page}"
            spec = st.session_state.draft_positions[page_key][st.session_state.selected_field]
            
            # Show current font size
            st.info(f"📝 Font Size: **{spec['font']} pt** (Fixed per field type)")
            
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.slider(
                    "X Position (inches)", 
                    0.0, 8.5, 
                    value=float(spec['x']), 
                    step=0.05,
                    key=f"slider_x_{page_key}_{st.session_state.selected_field}"
                )
                if new_x != spec['x']:
                    update_draft_position(page_key, st.session_state.selected_field, 'x', new_x)
                
            with col_y:
                new_y = st.slider(
                    "Y Position (inches)", 
                    0.0, 11.0, 
                    value=float(spec['y']), 
                    step=0.05,
                    key=f"slider_y_{page_key}_{st.session_state.selected_field}"
                )
                if new_y != spec['y']:
                    update_draft_position(page_key, st.session_state.selected_field, 'y', new_y)
            
            col_w, col_h = st.columns(2)
            with col_w:
                new_w = st.slider(
                    "Width (inches)", 
                    0.1, 8.0, 
                    value=float(spec['w']), 
                    step=0.05,
                    key=f"slider_w_{page_key}_{st.session_state.selected_field}"
                )
                if new_w != spec['w']:
                    update_draft_position(page_key, st.session_state.selected_field, 'w', new_w)
                
            with col_h:
                new_h = st.slider(
                    "Height (inches)", 
                    0.1, 3.0, 
                    value=float(spec['h']), 
                    step=0.05,
                    key=f"slider_h_{page_key}_{st.session_state.selected_field}"
                )
                if new_h != spec['h']:
                    update_draft_position(page_key, st.session_state.selected_field, 'h', new_h)
            
            if st.session_state.unsaved_changes[page_key]:
                st.warning(f"📌 Position changed: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\" (UNSAVED)")
            else:
                st.success(f"✅ Current saved position: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\"")
    
    with col2:
        st.header("🎛️ Controls")
        
        # Show current coordinates
        if st.button("📊 Show Current Coordinates", use_container_width=True):
            st.subheader("Saved Coordinates")
            for page_key, fields in st.session_state.saved_positions.items():
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
                st.dataframe(coord_data, use_container_width=True, height=250)
        
        st.markdown("---")
        
        # Font sizes display
        st.subheader("📝 Font Sizes")
        st.markdown("""
        **Page 1:**
        - Date: **20 pt**
        - Age & Gender: **16.1 pt**
        - Main Theme: **21 pt**
        - Case Summary: **18 pt**
        - Signature: **24 pt**
        
        **Page 2:**
        - EPA/Rubric: **14 pt**
        - Strengths/Improvements: **12 pt**
        """)
        
        st.markdown("---")
        
        st.subheader("📄 Process Forms")
        
        st.write(f"**📊 Cases to process:** {cases_count}")
        
        # Warning if there are unsaved changes
        if has_unsaved:
            st.error("❗ Save all changes before generating PDFs!")
        
        if cases_count == 0:
            st.warning("No valid cases found")
        else:
            # Preview first case
            if st.button("👁️ Preview First Case", use_container_width=True):
                try:
                    if st.session_state.cases_data and len(st.session_state.cases_data) > 0:
                        first_case = st.session_state.cases_data[0]
                        if isinstance(first_case, dict):
                            st.json(first_case)
                        else:
                            st.error(f"First case is invalid: {type(first_case).__name__}")
                    else:
                        st.warning("No cases available")
                except Exception as e:
                    st.error(f"Error previewing: {str(e)}")
            
            # Generate PDFs
            button_disabled = has_unsaved
            button_type = "secondary" if has_unsaved else "primary"
            
            if st.button("🚀 Fill All Forms", 
                        type=button_type, 
                        use_container_width=True,
                        disabled=button_disabled,
                        help="Save all changes first" if has_unsaved else "Generate PDFs with saved positions"):
                
                if not has_unsaved:  # Double-check
                    progress_bar = st.progress(0)
                    status_container = st.container()
                    
                    filled_pdfs = {}
                    failed_cases = []
                    
                    try:
                        # Process each case
                        for i, case in enumerate(st.session_state.cases_data):
                            if not isinstance(case, dict):
                                failed_cases.append(f"Case {i+1}: Invalid type")
                                continue
                            
                            case_id = case.get('case_id', f'case_{i+1:03d}')
                            
                            with status_container:
                                st.text(f"Processing {i+1}/{cases_count}: {case_id}")
                            
                            progress_bar.progress((i + 1) / cases_count)
                            
                            try:
                                # Create filled PDF using SAVED positions
                                filled_pdf = create_filled_pdf(case, st.session_state.pdf_bytes, st.session_state.font_bytes)
                                
                                if filled_pdf:
                                    filename = f"{case_id}_filled.pdf"
                                    filled_pdfs[filename] = filled_pdf
                                else:
                                    failed_cases.append(f"{case_id}: PDF creation returned None")
                            except Exception as e:
                                failed_cases.append(f"{case_id}: {str(e)}")
                        
                        # Create ZIP
                        if filled_pdfs:
                            zip_buffer = BytesIO()
                            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for filename, pdf_data in filled_pdfs.items():
                                    zip_file.writestr(filename, pdf_data)
                            
                            zip_buffer.seek(0)
                            
                            status_container.empty()
                            progress_bar.empty()
                            
                            if failed_cases:
                                st.warning(f"⚠️ Processed {len(filled_pdfs)} of {cases_count} forms")
                                with st.expander("Failed Cases"):
                                    for error in failed_cases:
                                        st.error(error)
                            else:
                                st.success(f"🎉 Successfully processed all {len(filled_pdfs)} forms with your saved positions!")
                                st.balloons()
                            
                            # Download button
                            st.download_button(
                                label=f"📥 Download {len(filled_pdfs)} Filled Forms (ZIP)",
                                data=zip_buffer.getvalue(),
                                file_name=f"medical_forms_{len(filled_pdfs)}_cases.zip",
                                mime="application/zip",
                                use_container_width=True
                            )
                            
                            # Show ZIP contents
                            with st.expander("📦 ZIP Contents"):
                                for filename in filled_pdfs.keys():
                                    st.text(f"✓ {filename}")
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
                        st.error(f"❌ Critical error: {str(e)}")
                        st.exception(e)
        
        st.markdown("---")
        st.subheader("📋 Instructions")
        st.markdown("""
        **How it works:**
        1. ✏️ **Adjust positions** using sliders
        2. 💾 **SAVE the page** before switching pages
        3. 🚀 **Generate PDFs** with saved positions
        
        **Important:**
        - ⚠️ Unsaved changes won't be used in PDFs
        - 💾 Save each page separately
        - ✅ Green checkmarks = saved positions
        """)

if __name__ == "__main__":
    main()
