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
from plotly import graph_objs as go
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

# Default field specifications with UPDATED PAGE 2 FONT SIZES
DEFAULT_SPECS = {
    "page1": {
        # PAGE 1 FONT SIZES UNCHANGED AS REQUESTED
        "date": {"x": 1.5, "y": 2.6, "w": 2.5, "h": 0.25, "font": 20},
        "age_gender": {"x": 2.2, "y": 3.0, "w": 3.0, "h": 0.25, "font": 16.1},
        "main_theme": {"x": 1.2, "y": 3.6, "w": 6.5, "h": 0.4, "font": 21},
        "case_summary": {"x": 0.8, "y": 4.3, "w": 7.0, "h": 1.5, "font": 18},
        "self_reflection_upper": {"x": 0.8, "y": 6.2, "w": 7.0, "h": 0.6, "font": 15},
        "self_reflection_lower": {"x": 0.8, "y": 7.0, "w": 7.0, "h": 1.0, "font": 15},
        "signature_mi": {"x": 0.8, "y": 9.8, "w": 3.0, "h": 0.3, "font": 24}
    },
    "page2": {
        # UPDATED PAGE 2 FONT SIZES AS SPECIFIED
        "epa_row1": {"x": 0.6, "y": 1.8, "w": 1.8, "h": 0.35, "font": 32},  # 32pt
        "epa_row2": {"x": 0.6, "y": 2.4, "w": 1.8, "h": 0.35, "font": 32},  # 32pt
        "epa_row3": {"x": 0.6, "y": 3.0, "w": 1.8, "h": 0.35, "font": 32},  # 32pt
        "epa_row4": {"x": 0.6, "y": 3.6, "w": 1.8, "h": 0.35, "font": 32},  # 32pt
        "rubric_row1": {"x": 2.5, "y": 1.8, "w": 1.5, "h": 0.35, "font": 24},  # 24pt
        "rubric_row2": {"x": 2.5, "y": 2.4, "w": 1.5, "h": 0.35, "font": 24},  # 24pt
        "rubric_row3": {"x": 2.5, "y": 3.0, "w": 1.5, "h": 0.35, "font": 24},  # 24pt
        "rubric_row4": {"x": 2.5, "y": 3.6, "w": 1.5, "h": 0.35, "font": 24},  # 24pt
        "strength_row1": {"x": 4.1, "y": 1.8, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "strength_row2": {"x": 4.1, "y": 2.4, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "strength_row3": {"x": 4.1, "y": 3.0, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "strength_row4": {"x": 4.1, "y": 3.6, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "improve_row1": {"x": 6.0, "y": 1.8, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "improve_row2": {"x": 6.0, "y": 2.4, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "improve_row3": {"x": 6.0, "y": 3.0, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
        "improve_row4": {"x": 6.0, "y": 3.6, "w": 1.8, "h": 0.35, "font": 16},  # 16pt
    }
}

def initialize_session_state():
    """Initialize session state with proper separation of saved and draft states"""
    
    # PERMANENT saved positions - these persist and are used for PDF generation
    if 'permanent_saved_positions' not in st.session_state:
        st.session_state.permanent_saved_positions = copy.deepcopy(DEFAULT_SPECS)
    
    # WORKING positions - these are being actively edited
    if 'working_positions' not in st.session_state:
        st.session_state.working_positions = copy.deepcopy(st.session_state.permanent_saved_positions)
    
    # Track if working positions differ from saved
    if 'has_unsaved_changes' not in st.session_state:
        st.session_state.has_unsaved_changes = {"page1": False, "page2": False}
    
    # Track shape dragging
    if 'shapes_modified' not in st.session_state:
        st.session_state.shapes_modified = False
    
    # Track field order for shape mapping
    if 'field_order' not in st.session_state:
        st.session_state.field_order = {}
    
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
        ('show_success_message', None),
        ('last_plotly_config', None)
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

def positions_differ(pos1, pos2):
    """Check if two position specs differ"""
    for key in ['x', 'y', 'w', 'h']:
        if abs(pos1[key] - pos2[key]) > 0.001:
            return True
    return False

def check_for_changes(page_key):
    """Check if working positions differ from saved for a specific page"""
    working = st.session_state.working_positions[page_key]
    saved = st.session_state.permanent_saved_positions[page_key]
    
    for field_name in working:
        if positions_differ(working[field_name], saved[field_name]):
            return True
    return False

def update_working_position(page_key, field_name, coord_type, value):
    """Update working position and mark page as having changes"""
    old_value = st.session_state.working_positions[page_key][field_name][coord_type]
    if abs(old_value - value) > 0.001:
        st.session_state.working_positions[page_key][field_name][coord_type] = value
        st.session_state.has_unsaved_changes[page_key] = check_for_changes(page_key)

def save_page_positions(page_key):
    """Commit working positions to permanent saved positions for a page"""
    st.session_state.permanent_saved_positions[page_key] = copy.deepcopy(
        st.session_state.working_positions[page_key]
    )
    st.session_state.has_unsaved_changes[page_key] = False
    st.session_state.show_success_message = f"Page {page_key[-1]} positions saved successfully!"

def reset_all_positions():
    """Reset all positions to defaults"""
    st.session_state.permanent_saved_positions = copy.deepcopy(DEFAULT_SPECS)
    st.session_state.working_positions = copy.deepcopy(DEFAULT_SPECS)
    st.session_state.has_unsaved_changes = {"page1": False, "page2": False}
    st.session_state.show_success_message = "All positions reset to defaults!"

def inches_to_pixels(inches, dpi=150):
    return int(inches * dpi)

def pixels_to_inches(pixels, dpi=150):
    return pixels / dpi

def extract_shape_positions(relayout_data, page_num, img_height):
    """Extract positions from Plotly relayout data after shape dragging"""
    if not relayout_data:
        return None
    
    # Look for shape modifications in relayout data
    modified_positions = {}
    page_key = f"page{page_num}"
    field_names = list(st.session_state.working_positions[page_key].keys())
    
    # Check each possible shape modification key
    for i, field_name in enumerate(field_names):
        # Plotly uses keys like 'shapes[0].x0', 'shapes[0].y0', etc.
        shape_key_prefix = f'shapes[{i}]'
        
        x0_key = f'{shape_key_prefix}.x0'
        y0_key = f'{shape_key_prefix}.y0'
        x1_key = f'{shape_key_prefix}.x1'
        y1_key = f'{shape_key_prefix}.y1'
        
        if any(key in relayout_data for key in [x0_key, y0_key, x1_key, y1_key]):
            # Get current positions as defaults
            current = st.session_state.working_positions[page_key][field_name]
            
            # Extract new positions if available
            if x0_key in relayout_data and x1_key in relayout_data:
                x0_px = relayout_data[x0_key]
                x1_px = relayout_data[x1_key]
                new_x = pixels_to_inches(x0_px)
                new_w = pixels_to_inches(x1_px - x0_px)
            else:
                new_x = current['x']
                new_w = current['w']
            
            if y0_key in relayout_data and y1_key in relayout_data:
                y0_px = relayout_data[y0_key]
                y1_px = relayout_data[y1_key]
                # Convert from bottom-origin to top-origin
                new_y = pixels_to_inches(img_height - y1_px)
                new_h = pixels_to_inches(y1_px - y0_px)
            else:
                new_y = current['y']
                new_h = current['h']
            
            modified_positions[field_name] = {
                'x': new_x,
                'y': new_y,
                'w': new_w,
                'h': new_h
            }
    
    return modified_positions if modified_positions else None

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
    
    if 'Date' in original_case:
        transformed['date'] = original_case['Date']
    
    if 'Age & Gender' in original_case:
        transformed['age_gender'] = original_case['Age & Gender']
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
    
    field_mappings = {
        'Main theme of the case': 'main_theme',
        'Case Summary': 'case_summary',
        'Signature of the MI': 'signature_mi'
    }
    
    for old_key, new_key in field_mappings.items():
        if old_key in original_case:
            transformed[new_key] = original_case[old_key]
    
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
    
    if 'case_id' not in transformed:
        date_part = transformed.get('date', '').replace('-', '')
        theme_part = transformed.get('main_theme', 'case')[:20].replace(' ', '_').replace('/', '_')
        transformed['case_id'] = f"case_{date_part}_{theme_part}" if date_part else f"case_{theme_part}"
    
    return transformed

def load_input_data():
    """Load all required data from the input folder"""
    if not os.path.exists(INPUT_FOLDER):
        st.session_state.loading_error = f"❌ Input folder not found at: {INPUT_FOLDER}"
        return False
    
    errors = []
    
    # Load PDF
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
    
    # Load cases
    cases_path = os.path.join(INPUT_FOLDER, CASES_FILE)
    if not os.path.exists(cases_path):
        errors.append(f"• Missing: {CASES_FILE}")
    else:
        try:
            with open(cases_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
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
        except Exception as e:
            errors.append(f"• Error loading {CASES_FILE}: {str(e)}")
            st.session_state.cases_data = []
    
    # Load font
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

def create_interactive_plotly_figure(page_num):
    """Create DRAGGABLE interactive Plotly figure"""
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
    
    # Store field order for shape mapping
    field_names = list(st.session_state.working_positions[page_key].keys())
    st.session_state.field_order[page_key] = field_names
    
    # Use WORKING positions for display
    for i, (field_name, spec) in enumerate(st.session_state.working_positions[page_key].items()):
        x_px = inches_to_pixels(spec['x'])
        y_px = img_height - inches_to_pixels(spec['y'] + spec['h'])
        w_px = inches_to_pixels(spec['w'])
        h_px = inches_to_pixels(spec['h'])
        
        color = colors[i % len(colors)]
        
        if field_name == st.session_state.selected_field:
            color = 'lime'
            opacity = 0.5
            line_width = 3
        else:
            opacity = 0.3
            line_width = 2
        
        # DRAGGABLE rectangles (editable=True)
        fig.add_shape(
            type="rect",
            x0=x_px, y0=y_px,
            x1=x_px + w_px, y1=y_px + h_px,
            line=dict(color=color, width=line_width),
            fillcolor=color,
            opacity=opacity,
            editable=True,  # DRAGGABLE!
            name=field_name,
            layer="above"
        )
        
        # Field label
        fig.add_annotation(
            x=x_px + w_px/2,
            y=y_px + h_px/2,
            text=f"<b>{field_name}</b><br>Font: {spec['font']}pt",
            showarrow=False,
            font=dict(size=9, color="white" if field_name == st.session_state.selected_field else "black"),
            bgcolor="rgba(0,0,0,0.7)" if field_name == st.session_state.selected_field else "rgba(255,255,255,0.7)",
            opacity=0.9
        )
    
    # Status indicator
    status = "⚠️ UNSAVED" if st.session_state.has_unsaved_changes[page_key] else "✅ SAVED"
    
    fig.update_layout(
        title=dict(
            text=f"📄 Page {page_num} - {status}<br>" +
                 f"<sub>🎯 Drag boxes OR use sliders to position fields</sub>",
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
        dragmode='pan',
        modebar=dict(remove=['toImage', 'select2d', 'lasso2d'])
    )
    
    # Enable shape editing
    fig.update_shapes(dict(editable=True))
    
    return fig

def create_filled_pdf(case_data, pdf_bytes, font_bytes=None):
    """Create filled PDF using PERMANENT saved positions with updated font sizes"""
    try:
        if not isinstance(case_data, dict):
            return None
            
        overlay_buffer = BytesIO()
        
        original = PdfReader(BytesIO(pdf_bytes))
        first_page = original.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
        
        # Setup font
        font_color = Color(0.102, 0.227, 0.486)
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
            if not text:
                return
            
            text = str(text).strip()
            if not text:
                return
            
            x_pts = spec['x'] * 72
            y_pts = (page_height/72 - spec['y'] - spec['h']/2) * 72
            w_pts = spec['w'] * 72
            
            # Use the font size from spec (includes updated Page 2 sizes)
            font_size = spec['font']
            c.setFont(font_name, font_size)
            c.setFillColor(font_color)
            
            # For larger font sizes, adjust line height
            if font_size > 20:
                line_height = font_size * 1.1
            else:
                line_height = font_size + 2
            
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
                
                start_y = y_pts + (len(lines) - 1) * line_height / 2
                
                for line in lines:
                    c.drawString(x_pts + 5, start_y, line)
                    start_y -= line_height
            else:
                c.drawString(x_pts + 5, y_pts, text)
        
        # Use PERMANENT saved positions
        saved_specs = st.session_state.permanent_saved_positions
        
        # PAGE 1 (font sizes unchanged as requested)
        page1_specs = saved_specs['page1']
        
        draw_text(case_data.get('date', ''), page1_specs['date'], page_height)
        
        if 'age_gender' in case_data:
            draw_text(case_data['age_gender'], page1_specs['age_gender'], page_height)
        else:
            age_gender = f"{case_data.get('age', '')} {case_data.get('gender', '')}".strip()
            draw_text(age_gender, page1_specs['age_gender'], page_height)
        
        draw_text(case_data.get('main_theme', ''), page1_specs['main_theme'], page_height)
        draw_text(case_data.get('case_summary', ''), page1_specs['case_summary'], page_height)
        
        reflection = case_data.get('self_reflection', {})
        if isinstance(reflection, dict):
            draw_text(reflection.get('what_did_right', ''), page1_specs['self_reflection_upper'], page_height)
            draw_text(reflection.get('needs_development', ''), page1_specs['self_reflection_lower'], page_height)
        
        draw_text(case_data.get('signature_mi', ''), page1_specs['signature_mi'], page_height)
        
        # PAGE 2 (with updated font sizes)
        c.showPage()
        page2_specs = saved_specs['page2']
        epa_data = case_data.get('epa_assessment', {})
        
        if isinstance(epa_data, dict):
            epas = epa_data.get('epa_tested', [])
            rubrics = epa_data.get('rubric_levels', [])
            strengths = epa_data.get('strength_points', [])
            improvements = epa_data.get('points_needing_improvement', [])
            
            epas = epas if isinstance(epas, list) else []
            rubrics = rubrics if isinstance(rubrics, list) else []
            strengths = strengths if isinstance(strengths, list) else []
            improvements = improvements if isinstance(improvements, list) else []
            
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
        
        # Merge
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
        return None

def main():
    """Main application with bidirectional drag-and-slider positioning"""
    
    initialize_session_state()
    
    if not st.session_state.data_loaded and not st.session_state.loading_error:
        with st.spinner("🔄 Loading data from /input folder..."):
            load_input_data()
    
    st.title("📋 PDF Medical Form Filler")
    st.markdown("*Interactive positioning: Drag boxes or use sliders*")
    
    # Error handling
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
    
    # Sidebar
    st.sidebar.header("📁 Data Status")
    st.sidebar.success(f"✅ PDF: {PDF_FILE}")
    
    cases_count = len(st.session_state.cases_data) if isinstance(st.session_state.cases_data, list) else 0
    st.sidebar.success(f"✅ Cases: {cases_count} loaded")
    
    if st.session_state.font_bytes:
        st.sidebar.success(f"✅ Font: {FONT_FILE}")
    else:
        st.sidebar.info(f"ℹ️ Using default font")
    
    st.sidebar.markdown("---")
    
    # Position Status
    st.sidebar.header("📍 Position Status")
    
    page1_changed = st.session_state.has_unsaved_changes["page1"]
    page2_changed = st.session_state.has_unsaved_changes["page2"]
    
    if page1_changed or page2_changed:
        st.sidebar.error("⚠️ **Unsaved Changes**")
        if page1_changed:
            st.sidebar.warning("• Page 1 modified")
        if page2_changed:
            st.sidebar.warning("• Page 2 modified")
        st.sidebar.info("💡 Click SAVE to commit")
    else:
        st.sidebar.success("✅ All changes saved")
    
    # Font sizes info
    st.sidebar.markdown("---")
    st.sidebar.subheader("📝 Font Sizes")
    
    with st.sidebar.expander("Page 1 Fonts", expanded=False):
        st.markdown("""
        - Date: **20pt**
        - Age/Gender: **16.1pt**
        - Theme: **21pt**
        - Summary: **18pt**
        - Reflection: **15pt**
        - Signature: **24pt**
        """)
    
    with st.sidebar.expander("Page 2 Fonts", expanded=False):
        st.markdown("""
        - EPA: **32pt**
        - Rubric: **24pt**
        - Strengths: **16pt**
        - Improvements: **16pt**
        """)
    
    # Reset button
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Reset All to Defaults", type="secondary", use_container_width=True):
        reset_all_positions()
        st.rerun()
    
    # Cases summary
    if cases_count > 0:
        st.sidebar.markdown("---")
        st.sidebar.subheader("📊 Cases")
        for i, case in enumerate(st.session_state.cases_data[:3]):
            date = case.get('date', 'No date')
            st.sidebar.text(f"{i+1}. {date}")
        if cases_count > 3:
            st.sidebar.text(f"... +{cases_count - 3} more")
    
    # Main content
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("🎯 Interactive Field Positioning")
        
        # Success message
        if st.session_state.show_success_message:
            st.success(f"✅ {st.session_state.show_success_message}")
            st.session_state.show_success_message = None
        
        # Instructions
        st.info("💡 **Two ways to position:** Drag the boxes directly on the image OR use the sliders below. Both sync automatically!")
        
        # Page selection and save
        col_page, col_field, col_save = st.columns([1, 2, 1])
        
        with col_page:
            page_option = st.selectbox("📄 Page", ["Page 1", "Page 2"], key="page_selector")
            current_page = 1 if page_option == "Page 1" else 2
            st.session_state.current_page = current_page
        
        with col_field:
            page_key = f"page{current_page}"
            field_names = list(st.session_state.working_positions[page_key].keys())
            
            if st.session_state.selected_field not in field_names:
                st.session_state.selected_field = field_names[0] if field_names else None
            
            if field_names:
                selected_field = st.selectbox(
                    "🎯 Field", 
                    field_names,
                    index=field_names.index(st.session_state.selected_field) if st.session_state.selected_field in field_names else 0,
                    key="field_selector"
                )
                st.session_state.selected_field = selected_field
        
        with col_save:
            page_key = f"page{current_page}"
            has_changes = st.session_state.has_unsaved_changes[page_key]
            
            if st.button(
                f"💾 **SAVE PAGE {current_page}**" if has_changes else f"✅ Page {current_page} Saved",
                type="primary" if has_changes else "secondary",
                disabled=not has_changes,
                use_container_width=True,
                key=f"save_button_{current_page}"
            ):
                save_page_positions(page_key)
                st.rerun()
        
        # Interactive Plotly figure with draggable shapes
        if current_page in st.session_state.pdf_images:
            fig = create_interactive_plotly_figure(current_page)
            if fig:
                # Render the Plotly chart
                st.plotly_chart(
                    fig, 
                    use_container_width=True, 
                    key=f"plotly_{current_page}"
                )
        
        # Position Controls (Sliders)
        st.subheader(f"⚙️ Fine-tune '{st.session_state.selected_field}' Position")
        
        if st.session_state.selected_field:
            page_key = f"page{current_page}"
            field_name = st.session_state.selected_field
            spec = st.session_state.working_positions[page_key][field_name]
            
            # Display font size
            st.markdown(f"**📝 Font Size:** {spec['font']}pt")
            
            # Position sliders
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.slider(
                    "↔️ X Position (inches)",
                    0.0, 8.5,
                    value=float(spec['x']),
                    step=0.01,
                    format="%.2f",
                    key=f"x_{page_key}_{field_name}",
                    help="Horizontal position from left"
                )
                if new_x != spec['x']:
                    update_working_position(page_key, field_name, 'x', new_x)
            
            with col_y:
                new_y = st.slider(
                    "↕️ Y Position (inches)",
                    0.0, 11.0,
                    value=float(spec['y']),
                    step=0.01,
                    format="%.2f",
                    key=f"y_{page_key}_{field_name}",
                    help="Vertical position from top"
                )
                if new_y != spec['y']:
                    update_working_position(page_key, field_name, 'y', new_y)
            
            col_w, col_h = st.columns(2)
            with col_w:
                new_w = st.slider(
                    "📐 Width (inches)",
                    0.1, 8.0,
                    value=float(spec['w']),
                    step=0.01,
                    format="%.2f",
                    key=f"w_{page_key}_{field_name}",
                    help="Field width"
                )
                if new_w != spec['w']:
                    update_working_position(page_key, field_name, 'w', new_w)
            
            with col_h:
                new_h = st.slider(
                    "📏 Height (inches)",
                    0.1, 3.0,
                    value=float(spec['h']),
                    step=0.01,
                    format="%.2f",
                    key=f"h_{page_key}_{field_name}",
                    help="Field height"
                )
                if new_h != spec['h']:
                    update_working_position(page_key, field_name, 'h', new_h)
            
            # Update button to sync dragged positions to sliders
            if st.button("🔄 Sync Dragged Positions", use_container_width=True, 
                        help="Click after dragging boxes to update slider values"):
                st.rerun()
            
            # Status
            if st.session_state.has_unsaved_changes[page_key]:
                st.warning(f"⚠️ Position: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\" (UNSAVED)")
            else:
                st.success(f"✅ Saved: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\"")
    
    with col2:
        st.header("🎛️ Tools")
        
        # Coordinate display
        if st.button("📋 Show All Positions", use_container_width=True):
            st.subheader("Current Positions")
            for pk in ["page1", "page2"]:
                st.write(f"**{pk.upper()}:**")
                data = []
                positions = st.session_state.permanent_saved_positions[pk]
                for fn, sp in positions.items():
                    data.append({
                        'Field': fn.replace('_', ' ').title()[:15],
                        'X': f"{sp['x']:.2f}",
                        'Y': f"{sp['y']:.2f}",
                        'W': f"{sp['w']:.2f}",
                        'H': f"{sp['h']:.2f}",
                        'Font': f"{sp['font']}"
                    })
                st.dataframe(data, use_container_width=True, height=200)
        
        st.markdown("---")
        
        # Generate PDFs
        st.subheader("📄 Generate PDFs")
        
        st.write(f"**Cases:** {cases_count}")
        
        has_any_unsaved = page1_changed or page2_changed
        
        if has_any_unsaved:
            st.error("💾 Save changes first!")
        
        if cases_count > 0:
            if st.button(
                "🚀 Generate All PDFs",
                type="primary" if not has_any_unsaved else "secondary",
                disabled=has_any_unsaved,
                use_container_width=True,
                help="Save all changes first" if has_any_unsaved else "Generate PDFs"
            ):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                filled_pdfs = {}
                failed_cases = []
                
                try:
                    for i, case in enumerate(st.session_state.cases_data):
                        if not isinstance(case, dict):
                            failed_cases.append(f"Case {i+1}: Invalid")
                            continue
                        
                        case_id = case.get('case_id', f'case_{i+1:03d}')
                        status_text.text(f"Processing {i+1}/{cases_count}")
                        progress_bar.progress((i + 1) / cases_count)
                        
                        try:
                            filled_pdf = create_filled_pdf(
                                case, 
                                st.session_state.pdf_bytes, 
                                st.session_state.font_bytes
                            )
                            
                            if filled_pdf:
                                filename = f"{case_id}_filled.pdf"
                                filled_pdfs[filename] = filled_pdf
                        except Exception as e:
                            failed_cases.append(f"{case_id}: {str(e)[:50]}")
                    
                    status_text.empty()
                    progress_bar.empty()
                    
                    if filled_pdfs:
                        # Create ZIP
                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for filename, pdf_data in filled_pdfs.items():
                                zf.writestr(filename, pdf_data)
                        
                        zip_buffer.seek(0)
                        
                        st.success(f"✅ Generated {len(filled_pdfs)} PDFs!")
                        
                        st.download_button(
                            label=f"💾 Download ZIP ({len(filled_pdfs)} PDFs)",
                            data=zip_buffer.getvalue(),
                            file_name=f"filled_forms_{len(filled_pdfs)}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                        
                        if failed_cases:
                            with st.expander("⚠️ Issues"):
                                for err in failed_cases:
                                    st.text(err)
                        
                        st.balloons()
                    else:
                        st.error("❌ No PDFs generated")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    status_text.empty()
                    progress_bar.empty()
        
        st.markdown("---")
        
        # Help
        st.subheader("❓ Help")
        st.markdown("""
        **Positioning:**
        - 🖱️ Drag boxes on image
        - 🎚️ OR use sliders
        - 🔄 Click Sync button
        - 💾 Save the page
        
        **Generate:**
        - Save all changes
        - Click Generate PDFs
        """)

if __name__ == "__main__":
    main()
