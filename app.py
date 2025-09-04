import json
import os
import zipfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import Color
from PyPDF2 import PdfWriter, PdfReader
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

def fill_medical_forms_with_corrected_coordinates():
    """
    Fill medical forms using the corrected coordinates from the positioning interface
    """
    
    # PASTE YOUR CORRECTED COORDINATES HERE (from the interface)
    # Replace this with the exported coordinates from the positioning interface
    corrected_coordinates = {
        "field_coordinates": {
            "page1": {
                "date": {"x": 2.87, "y": 3.65, "w": 1.75, "h": 0.31, "font": 20},
                "age_gender": {"x": 2.87, "y": 3.04, "w": 3.21, "h": 0.25, "font": 16.1},
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
    }
    
    # Load cases data
    print("📂 Loading cases data...")
    with open('/kaggle/input/handwriting-samples/cases_data.json', 'r') as f:
        cases_data = json.load(f)
    
    print(f"📋 Found {len(cases_data)} cases to process")
    
    # Setup font
    font_color = Color(0.102, 0.227, 0.486)  # #1A3A7C
    
    # Try to load custom font, fallback to Helvetica
    try:
        font_path = '/kaggle/input/handwriting-samples/AzzamHandwriting-Regular.ttf'
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('CustomFont', font_path))
            font_name = 'CustomFont'
            print("✅ Custom font loaded successfully")
        else:
            font_name = 'Helvetica'
            print("⚠️ Custom font not found, using Helvetica")
    except:
        font_name = 'Helvetica'
        print("⚠️ Error loading custom font, using Helvetica")
    
    # Create output directory
    output_dir = '/kaggle/working/filled_forms'
    os.makedirs(output_dir, exist_ok=True)
    
    filled_files = []
    field_coords = corrected_coordinates["field_coordinates"]
    
    print("\n🖊️ Starting form filling process...")
    
    for i, case in enumerate(cases_data, 1):
        try:
            print(f"📄 Processing case {i}: {case.get('case_id', f'Case_{i}')}")
            
            # Create overlay PDF with text
            overlay_buffer = BytesIO()
            
            # Determine page size from original
            with open('/kaggle/input/handwriting-samples/empty_form.pdf', 'rb') as f:
                original = PdfReader(f)
                first_page = original.pages[0]
                page_width = float(first_page.mediabox.width)
                page_height = float(first_page.mediabox.height)
            
            # Convert points to inches for page size
            page_size = (page_width, page_height)
            c = canvas.Canvas(overlay_buffer, pagesize=page_size)
            
            def draw_centered_text(canvas_obj, text, spec, page_height):
                """Draw text centered in the specified area"""
                if not text or not isinstance(text, str):
                    return
                
                # Convert inches to points (1 inch = 72 points)
                x_points = spec['x'] * 72
                y_points = (page_height/72 - spec['y'] - spec['h']/2) * 72  # Adjust Y for PDF coordinate system
                width_points = spec['w'] * 72
                height_points = spec['h'] * 72
                
                # Set font
                canvas_obj.setFont(font_name, spec['font'])
                canvas_obj.setFillColor(font_color)
                
                # Handle long text by wrapping
                max_width = width_points - 10  # Small margin
                
                if len(text) > 50:  # Long text, wrap it
                    words = text.split()
                    lines = []
                    current_line = ""
                    
                    for word in words:
                        test_line = current_line + " " + word if current_line else word
                        text_width = canvas_obj.stringWidth(test_line, font_name, spec['font'])
                        
                        if text_width <= max_width:
                            current_line = test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                                current_line = word
                            else:
                                lines.append(word)  # Single word is too long
                    
                    if current_line:
                        lines.append(current_line)
                    
                    # Draw multiple lines centered
                    line_height = spec['font'] + 2
                    total_text_height = len(lines) * line_height
                    start_y = y_points + (height_points - total_text_height) / 2 + total_text_height - line_height
                    
                    for line in lines:
                        text_width = canvas_obj.stringWidth(line, font_name, spec['font'])
                        text_x = x_points + (width_points - text_width) / 2
                        canvas_obj.drawString(text_x, start_y, line)
                        start_y -= line_height
                
                else:  # Short text, single line
                    text_width = canvas_obj.stringWidth(text, font_name, spec['font'])
                    text_x = x_points + (width_points - text_width) / 2
                    canvas_obj.drawString(text_x, y_points, text)
            
            # Page 1 - Fill fields
            print(f"  📝 Filling page 1 fields...")
            
            # Date
            date_text = case.get('date', '')
            if date_text:
                draw_centered_text(c, date_text, field_coords['page1']['date'], page_height)
            
            # Age & Gender
            age = case.get('age', '')
            gender = case.get('gender', '')
            age_gender_text = f"{age} {gender}".strip()
            if age_gender_text:
                draw_centered_text(c, age_gender_text, field_coords['page1']['age_gender'], page_height)
            
            # Main theme
            main_theme = case.get('main_theme', '')
            if main_theme:
                draw_centered_text(c, main_theme, field_coords['page1']['main_theme'], page_height)
            
            # Case summary
            case_summary = case.get('case_summary', '')
            if case_summary:
                draw_centered_text(c, case_summary, field_coords['page1']['case_summary'], page_height)
            
            # Self reflection upper
            reflection_upper = case.get('self_reflection', {}).get('what_did_right', '')
            if reflection_upper:
                draw_centered_text(c, reflection_upper, field_coords['page1']['self_reflection_upper'], page_height)
            
            # Self reflection lower
            reflection_lower = case.get('self_reflection', {}).get('needs_development', '')
            if reflection_lower:
                draw_centered_text(c, reflection_lower, field_coords['page1']['self_reflection_lower'], page_height)
            
            # Start page 2
            c.showPage()
            
            # Page 2 - Fill EPA table
            print(f"  📊 Filling page 2 EPA table...")
            
            epa_data = case.get('epa_assessment', {})
            
            # EPA columns
            epas = epa_data.get('epa_tested', ['EPA 2', 'EPA 6', 'EPA 9', 'EPA 12'])
            for idx, epa in enumerate(epas[:4]):  # Max 4 rows
                field_key = f'epa_row{idx+1}'
                if field_key in field_coords['page2']:
                    draw_centered_text(c, str(epa), field_coords['page2'][field_key], page_height)
            
            # Rubric columns
            rubrics = epa_data.get('rubric_levels', ['Level C', 'Level C', 'Level C', 'Level C'])
            for idx, rubric in enumerate(rubrics[:4]):
                field_key = f'rubric_row{idx+1}'
                if field_key in field_coords['page2']:
                    draw_centered_text(c, str(rubric), field_coords['page2'][field_key], page_height)
            
            # Strength columns
            strengths = epa_data.get('strength_points', [
                'Hydration grading', 'ORS coaching', 'Clear notes', 'Return plan'
            ])
            for idx, strength in enumerate(strengths[:4]):
                field_key = f'strength_row{idx+1}'
                if field_key in field_coords['page2']:
                    draw_centered_text(c, str(strength), field_coords['page2'][field_key], page_height)
            
            # Improvement columns  
            improvements = epa_data.get('points_needing_improvement', [
                'Orthostatic vitals', 'Diet specifics', 'Weight charting', 'Phone followup'
            ])
            for idx, improvement in enumerate(improvements[:4]):
                field_key = f'improve_row{idx+1}'
                if field_key in field_coords['page2']:
                    draw_centered_text(c, str(improvement), field_coords['page2'][field_key], page_height)
            
            c.save()
            overlay_buffer.seek(0)
            
            # Merge with original form
            print(f"  🔄 Merging with original form...")
            original_pdf = PdfReader('/kaggle/input/handwriting-samples/empty_form.pdf')
            overlay_pdf = PdfReader(overlay_buffer)
            
            writer = PdfWriter()
            
            # Merge each page
            for page_num in range(len(original_pdf.pages)):
                original_page = original_pdf.pages[page_num]
                if page_num < len(overlay_pdf.pages):
                    overlay_page = overlay_pdf.pages[page_num]
                    original_page.merge_page(overlay_page)
                writer.add_page(original_page)
            
            # Save filled form
            case_id = case.get('case_id', f'case_{i}')
            output_filename = f"{case_id}_filled.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            filled_files.append(output_path)
            print(f"  ✅ Saved: {output_filename}")
            
        except Exception as e:
            print(f"  ❌ Error processing case {i}: {str(e)}")
            continue
    
    # Create ZIP archive
    print(f"\n📦 Creating ZIP archive with {len(filled_files)} filled forms...")
    zip_path = '/kaggle/working/filled_medical_forms.zip'
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in filled_files:
            arcname = os.path.basename(file_path)
            zipf.write(file_path, arcname)
    
    print(f"✅ ZIP archive created: {zip_path}")
    print(f"📊 Summary:")
    print(f"   • Total cases processed: {len(filled_files)}")
    print(f"   • ZIP file size: {os.path.getsize(zip_path) / 1024 / 1024:.1f} MB")
    print(f"   • Output location: {zip_path}")
    
    return zip_path, filled_files

# Instructions for use
print("🎯 PDF Form Filler with Corrected Coordinates")
print("=" * 50)
print()
print("📋 INSTRUCTIONS:")
print("1. First run the positioning interface above")
print("2. Drag the red boxes to correct positions")
print("3. Click 'Export Coordinates' and copy the result")
print("4. Replace the 'corrected_coordinates' variable in this script")
print("5. Run this script to fill all forms with correct positioning")
print()
print("⚠️  IMPORTANT: Update the 'corrected_coordinates' variable with your exported data!")
print()

# Uncomment the line below to run the form filler (after updating coordinates)
# zip_path, files = fill_medical_forms_with_corrected_coordinates()
