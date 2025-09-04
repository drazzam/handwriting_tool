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

# Initialize session state
if 'field_specs' not in st.session_state:
    st.session_state.field_specs = {
        "page1": {
            "date": {"x": 2.87, "y": 3.65, "w": 1.75, "h": 0.31, "font": 20},
            "age_gender": {"x": 2.87, "y": 3.04, "w": 3.21, "h": 0.25, "font": 16},
            "main_theme": {"x": 2.74, "y": 4.42, "w": 5.25, "h": 0.5, "font": 21},
            "case_summary": {"x": 0.34, "y": 5.25, "w": 7.70, "h": 1.04, "font": 18},
            "self_reflection_upper": {"x": 2.15, "y": 6.34, "w": 5.84, "h": 0.66, "font": 15},
            "self_reflection_lower": {"x": 4.00, "y": 7.12, "w": 4.00, "h": 1.17, "font": 15}
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
    
    # Load cases data
    cases_path = os.path.join(INPUT_FOLDER, CASES_FILE)
    if not os.path.exists(cases_path):
        errors.append(f"• Missing: {CASES_FILE}")
    else:
        try:
            with open(cases_path, 'r', encoding='utf-8') as f:
                st.session_state.cases_data = json.load(f)
            if not st.session_state.cases_data:
                errors.append(f"• Empty or invalid: {CASES_FILE}")
        except Exception as e:
            errors.append(f"• Error loading {CASES_FILE}: {str(e)}")
    
    # Load font (optional)
    font_path = os.path.join(INPUT_FOLDER, FONT_FILE)
    if os.path.exists(font_path):
        try:
            with open(font_path, 'rb') as f:
                st.session_state.font_bytes = f.read()
        except Exception as e:
            # Font is optional, so just warn
            st.warning(f"Could not load custom font: {str(e)}")
    
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
    """Create filled PDF for a single case"""
    try:
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
        
        # Fill Page 1
        page1 = st.session_state.field_specs['page1']
        
        draw_text(case_data.get('date', ''), page1['date'], page_height)
        
        age_gender = f"{case_data.get('age', '')} {case_data.get('gender', '')}".strip()
        draw_text(age_gender, page1['age_gender'], page_height)
        
        draw_text(case_data.get('main_theme', ''), page1['main_theme'], page_height)
        draw_text(case_data.get('case_summary', ''), page1['case_summary'], page_height)
        
        reflection = case_data.get('self_reflection', {})
        draw_text(reflection.get('what_did_right', ''), page1['self_reflection_upper'], page_height)
        draw_text(reflection.get('needs_development', ''), page1['self_reflection_lower'], page_height)
        
        # Page 2
        c.showPage()
        page2 = st.session_state.field_specs['page2']
        epa_data = case_data.get('epa_assessment', {})
        
        # Fill EPA table
        epas = epa_data.get('epa_tested', ['EPA 2', 'EPA 6', 'EPA 9', 'EPA 12'])[:4]
        rubrics = epa_data.get('rubric_levels', ['Level C'] * 4)[:4]
        strengths = epa_data.get('strength_points', ['Good work'] * 4)[:4]
        improvements = epa_data.get('points_needing_improvement', ['Keep practicing'] * 4)[:4]
        
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
        st.error(f"Error creating PDF: {str(e)}")
        return None

def main():
    """Main application"""
    
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
            
            **Troubleshooting:**
            - Ensure the `/input` folder exists in your repository
            - Check that filenames match exactly (case-sensitive)
            - Verify file formats: PDF, JSON, TTF/OTF
            - Make sure files are not corrupted
            
            **Current input folder location:** `{INPUT_FOLDER}`
            """)
        
        if st.button("🔄 Retry Loading Data"):
            st.session_state.data_loaded = False
            st.session_state.loading_error = None
            st.experimental_rerun()
        
        return
    
    # Show data status in sidebar
    st.sidebar.header("📁 Loaded Data")
    st.sidebar.success(f"✅ PDF Template: {PDF_FILE}")
    st.sidebar.success(f"✅ Cases: {len(st.session_state.cases_data)} loaded")
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
        
        # Page and field selection
        col_page, col_field = st.columns([1, 2])
        
        with col_page:
            page_option = st.selectbox("📄 Select Page", ["Page 1", "Page 2"])
            current_page = 1 if page_option == "Page 1" else 2
            st.session_state.current_page = current_page
        
        with col_field:
            page_key = f"page{current_page}"
            field_names = list(st.session_state.field_specs[page_key].keys())
            selected_field = st.selectbox("🎯 Select Field", field_names, key="field_selector")
            st.session_state.selected_field = selected_field
        
        # Create and display interactive Plotly figure
        if current_page in st.session_state.pdf_images:
            fig = create_interactive_plotly_figure(current_page)
            
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"plotly_fig_{current_page}")
                
                st.info("💡 **Tip:** Drag the colored rectangles directly on the PDF to reposition fields. Green = selected field.")
        
        # Precise adjustment controls
        st.subheader(f"📐 Fine-tune '{st.session_state.selected_field}' Position")
        
        if st.session_state.selected_field:
            page_key = f"page{current_page}"
            spec = st.session_state.field_specs[page_key][st.session_state.selected_field]
            
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.slider("X Position (inches)", 0.0, 8.5, spec['x'], 0.05, 
                                key=f"x_slider_{st.session_state.selected_field}")
            with col_y:
                new_y = st.slider("Y Position (inches)", 0.0, 11.0, spec['y'], 0.05,
                                key=f"y_slider_{st.session_state.selected_field}")
            
            col_w, col_h = st.columns(2)
            with col_w:
                new_w = st.slider("Width (inches)", 0.1, 8.0, spec['w'], 0.05,
                                key=f"w_slider_{st.session_state.selected_field}")
            with col_h:
                new_h = st.slider("Height (inches)", 0.1, 3.0, spec['h'], 0.05,
                                key=f"h_slider_{st.session_state.selected_field}")
            
            # Update field specs from sliders
            st.session_state.field_specs[page_key][st.session_state.selected_field].update({
                'x': round(new_x, 2),
                'y': round(new_y, 2),
                'w': round(new_w, 2),
                'h': round(new_h, 2)
            })
            
            # Show current values
            st.success(f"📍 **{st.session_state.selected_field}**: X={new_x:.2f}\", Y={new_y:.2f}\", W={new_w:.2f}\", H={new_h:.2f}\"")
    
    with col2:
        st.header("🎛️ Controls")
        
        # Quick field selector
        st.subheader("📋 Quick Field Selection")
        page_key = f"page{current_page}"
        for field_name in st.session_state.field_specs[page_key].keys():
            if st.button(f"📍 {field_name.replace('_', ' ').title()}", key=f"quick_{field_name}"):
                st.session_state.selected_field = field_name
                st.experimental_rerun()
        
        st.markdown("---")
        
        # Coordinate display
        if st.button("📊 Show All Coordinates"):
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
        
        # Form processing
        st.subheader("📄 Process Forms")
        
        cases_count = len(st.session_state.cases_data)
        st.write(f"**📊 Cases to process:** {cases_count}")
        
        if cases_count == 0:
            st.warning("No cases found in data file")
        else:
            if st.button("🚀 Fill All Forms", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                filled_pdfs = {}
                
                for i, case in enumerate(st.session_state.cases_data):
                    status_text.text(f"Processing case {i+1}/{cases_count}: {case.get('case_id', f'Case {i+1}')}")
                    progress_bar.progress((i + 1) / cases_count)
                    
                    case_id = case.get('case_id', f'case_{i+1}')
                    filled_pdf = create_filled_pdf(case, st.session_state.pdf_bytes, st.session_state.font_bytes)
                    
                    if filled_pdf:
                        filled_pdfs[f"{case_id}_filled.pdf"] = filled_pdf
                
                # Create ZIP file
                if filled_pdfs:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename, pdf_data in filled_pdfs.items():
                            zip_file.writestr(filename, pdf_data)
                    
                    zip_buffer.seek(0)
                    
                    # Success message and download
                    status_text.empty()
                    progress_bar.empty()
                    
                    st.success(f"🎉 Successfully processed {len(filled_pdfs)} forms!")
                    st.balloons()
                    
                    st.download_button(
                        label="📥 Download Filled Forms (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="filled_medical_forms.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                else:
                    st.error("❌ No forms were successfully processed")
        
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
        1. Position all fields
        2. Click "Fill All Forms"  
        3. Download ZIP file
        
        **💡 Tips:**
        - Data loads from `/input` folder
        - Drag rectangles for quick positioning
        - Use sliders for precision
        """)

if __name__ == "__main__":
    main()
