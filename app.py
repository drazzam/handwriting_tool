import streamlit as st
import json
import zipfile
import os
import tempfile
import base64
from io import BytesIO
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfWriter, PdfReader
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="PDF Form Filler",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

if 'pdf_images' not in st.session_state:
    st.session_state.pdf_images = {}

if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = {}

# Helper functions
@st.cache_data
def load_pdf_as_images(pdf_bytes):
    """Convert PDF to images"""
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
        st.error(f"Error loading PDF: {str(e)}")
        return {}

def inches_to_pixels(inches, dpi=150):
    return int(inches * dpi)

def pixels_to_inches(pixels, dpi=150):
    return pixels / dpi

def create_field_overlay(img, page_key, selected_field=None):
    """Create overlay with field rectangles"""
    from PIL import Image, ImageDraw, ImageFont
    
    img_pil = Image.fromarray(img)
    overlay = Image.new('RGBA', img_pil.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    colors = [
        (255, 0, 0, 100),      # red
        (0, 0, 255, 100),      # blue
        (0, 255, 0, 100),      # green
        (255, 165, 0, 100),    # orange
        (128, 0, 128, 100),    # purple
        (165, 42, 42, 100),    # brown
        (255, 192, 203, 100),  # pink
        (128, 128, 128, 100),  # gray
        (128, 128, 0, 100),    # olive
        (0, 255, 255, 100),    # cyan
    ]
    
    dpi = 150
    
    for i, (field_name, spec) in enumerate(st.session_state.field_specs[page_key].items()):
        x = inches_to_pixels(spec['x'], dpi)
        y = inches_to_pixels(spec['y'], dpi)
        w = inches_to_pixels(spec['w'], dpi)
        h = inches_to_pixels(spec['h'], dpi)
        
        # Different color for selected field
        if field_name == selected_field:
            color = (0, 255, 0, 150)  # bright green
            outline = (0, 255, 0, 255)
            width = 4
        else:
            color = colors[i % len(colors)]
            outline = tuple(list(color[:3]) + [255])
            width = 2
        
        # Draw rectangle
        draw.rectangle([x, y, x+w, y+h], fill=color, outline=outline, width=width)
        
        # Draw label
        label_x = x + w//2
        label_y = y + h//2
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Get text size
        bbox = draw.textbbox((0, 0), field_name, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Draw text background
        text_bg = (0, 0, 0, 200) if field_name == selected_field else (255, 255, 255, 200)
        draw.rectangle([label_x - text_w//2 - 2, label_y - text_h//2 - 2,
                       label_x + text_w//2 + 2, label_y + text_h//2 + 2], fill=text_bg)
        
        # Draw text
        text_color = (255, 255, 255) if field_name == selected_field else (0, 0, 0)
        draw.text((label_x - text_w//2, label_y - text_h//2), field_name, 
                 fill=text_color, font=font)
    
    # Combine original image with overlay
    combined = Image.alpha_composite(img_pil.convert('RGBA'), overlay)
    return np.array(combined.convert('RGB'))

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
                # Save font to temporary file
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

# Main app
def main():
    st.title("📋 PDF Medical Form Filler")
    st.markdown("Interactive tool for positioning and filling medical forms")
    
    # Sidebar for file uploads
    st.sidebar.header("📁 Upload Files")
    
    # File uploads
    pdf_file = st.sidebar.file_uploader(
        "Upload PDF Template", 
        type=['pdf'],
        help="Upload your empty medical form template (PDF)"
    )
    
    cases_file = st.sidebar.file_uploader(
        "Upload Cases Data", 
        type=['json'],
        help="Upload JSON file containing case data"
    )
    
    font_file = st.sidebar.file_uploader(
        "Upload Custom Font (Optional)", 
        type=['ttf', 'otf'],
        help="Upload custom font file (optional)"
    )
    
    # Store uploaded files in session state
    if pdf_file:
        st.session_state.uploaded_files['pdf'] = pdf_file.read()
        st.session_state.pdf_images = load_pdf_as_images(st.session_state.uploaded_files['pdf'])
    
    if cases_file:
        st.session_state.uploaded_files['cases'] = json.loads(cases_file.read())
    
    if font_file:
        st.session_state.uploaded_files['font'] = font_file.read()
    
    # Check if required files are uploaded
    if 'pdf' not in st.session_state.uploaded_files:
        st.info("👆 Please upload your PDF template to get started")
        return
    
    if 'cases' not in st.session_state.uploaded_files:
        st.info("👆 Please upload your cases data (JSON) to continue")
        return
    
    # Main interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("🎯 Field Positioning")
        
        # Page selector
        page_option = st.selectbox("Select Page", ["Page 1", "Page 2"])
        current_page = 1 if page_option == "Page 1" else 2
        st.session_state.current_page = current_page
        
        # Display PDF with overlays
        if current_page in st.session_state.pdf_images:
            page_key = f"page{current_page}"
            
            # Field selector
            field_names = list(st.session_state.field_specs[page_key].keys())
            selected_field = st.selectbox("Select Field to Adjust", field_names)
            
            # Create image with overlays
            img_with_overlay = create_field_overlay(
                st.session_state.pdf_images[current_page], 
                page_key, 
                selected_field
            )
            
            st.image(img_with_overlay, caption=f"Page {current_page} - Green = Selected Field", use_column_width=True)
            
            # Position adjustment controls
            st.subheader(f"📐 Adjust '{selected_field}' Position")
            
            spec = st.session_state.field_specs[page_key][selected_field]
            
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.slider("X Position (inches)", 0.0, 8.5, spec['x'], 0.05, key=f"x_{selected_field}")
            with col_y:
                new_y = st.slider("Y Position (inches)", 0.0, 11.0, spec['y'], 0.05, key=f"y_{selected_field}")
            
            col_w, col_h = st.columns(2)
            with col_w:
                new_w = st.slider("Width (inches)", 0.1, 8.0, spec['w'], 0.05, key=f"w_{selected_field}")
            with col_h:
                new_h = st.slider("Height (inches)", 0.1, 3.0, spec['h'], 0.05, key=f"h_{selected_field}")
            
            # Update field specs
            st.session_state.field_specs[page_key][selected_field].update({
                'x': round(new_x, 2),
                'y': round(new_y, 2),
                'w': round(new_w, 2),
                'h': round(new_h, 2)
            })
    
    with col2:
        st.header("🎛️ Controls")
        
        # Show current coordinates
        if st.button("📊 Show All Coordinates"):
            st.subheader("Current Coordinates")
            for page_key, fields in st.session_state.field_specs.items():
                st.write(f"**{page_key.upper()}:**")
                coord_data = []
                for field_name, spec in fields.items():
                    coord_data.append({
                        'Field': field_name,
                        'X': f"{spec['x']:.2f}\"",
                        'Y': f"{spec['y']:.2f}\"",
                        'W': f"{spec['w']:.2f}\"",
                        'H': f"{spec['h']:.2f}\"",
                        'Font': spec['font']
                    })
                st.table(coord_data)
        
        st.markdown("---")
        
        # Form processing
        st.subheader("📄 Process Forms")
        
        cases_count = len(st.session_state.uploaded_files.get('cases', []))
        st.write(f"**Cases to process:** {cases_count}")
        
        if st.button("🚀 Fill All Forms", type="primary"):
            if cases_count > 0:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                filled_pdfs = {}
                pdf_bytes = st.session_state.uploaded_files['pdf']
                font_bytes = st.session_state.uploaded_files.get('font')
                
                for i, case in enumerate(st.session_state.uploaded_files['cases']):
                    status_text.text(f"Processing case {i+1}/{cases_count}...")
                    progress_bar.progress((i + 1) / cases_count)
                    
                    case_id = case.get('case_id', f'case_{i+1}')
                    filled_pdf = create_filled_pdf(case, pdf_bytes, font_bytes)
                    
                    if filled_pdf:
                        filled_pdfs[f"{case_id}_filled.pdf"] = filled_pdf
                
                # Create ZIP file
                if filled_pdfs:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename, pdf_data in filled_pdfs.items():
                            zip_file.writestr(filename, pdf_data)
                    
                    zip_buffer.seek(0)
                    
                    # Download button
                    st.success(f"✅ Successfully processed {len(filled_pdfs)} forms!")
                    st.download_button(
                        label="📥 Download Filled Forms (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="filled_medical_forms.zip",
                        mime="application/zip"
                    )
                else:
                    st.error("❌ No forms were successfully processed")
        
        # Instructions
        st.markdown("---")
        st.subheader("📋 Instructions")
        st.markdown("""
        1. **Upload Files**: PDF template and cases JSON
        2. **Select Page**: Choose Page 1 or Page 2
        3. **Select Field**: Pick field to adjust
        4. **Adjust Position**: Use sliders to position field
        5. **Repeat**: Adjust all fields as needed
        6. **Process**: Click "Fill All Forms" when ready
        7. **Download**: Get your completed forms as ZIP
        
        **Colors:**
        - 🟢 **Green**: Selected field
        - 🔴 **Red/Blue/etc**: Other fields
        """)

if __name__ == "__main__":
    main()
