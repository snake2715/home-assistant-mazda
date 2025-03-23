#!/usr/bin/env python3
"""
Fix script to replace all instances of RequestPriority.LOW with RequestPriority.BACKGROUND
in Mazda Connected Services integration files.
"""
import os
import re
import sys

def replace_in_file(file_path):
    """Replace all instances of RequestPriority.LOW with RequestPriority.BACKGROUND in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Check if the file contains the pattern
        if 'RequestPriority.LOW' in content:
            # Replace all occurrences
            modified_content = content.replace('RequestPriority.LOW', 'RequestPriority.BACKGROUND')
            
            # Write the modified content back to the file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(modified_content)
            
            print(f"✅ Fixed: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"❌ Error processing {file_path}: {str(e)}")
        return False

def scan_directory(directory):
    """Scan a directory recursively for Python files and fix them."""
    fixed_files = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if replace_in_file(file_path):
                    fixed_files += 1
    
    return fixed_files

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    custom_components_dir = os.path.join(base_dir, 'custom_components', 'mazda_cs')
    
    if not os.path.exists(custom_components_dir):
        print(f"❌ Directory not found: {custom_components_dir}")
        sys.exit(1)
    
    print(f"🔍 Scanning directory: {custom_components_dir}")
    fixed_count = scan_directory(custom_components_dir)
    
    print(f"\n✅ Fixed {fixed_count} files")
    if fixed_count > 0:
        print("\n⚠️  Don't forget to deploy these changes to your Home Assistant system!")
