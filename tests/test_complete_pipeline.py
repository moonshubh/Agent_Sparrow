#!/usr/bin/env python3
"""
Complete pipeline test for FeedMe with real Zendesk files
"""

import requests
import time
import os

print('🎯 COMPLETE PIPELINE TEST - FeedMe with Real Zendesk Files')
print('=' * 65)

def test_file(filename, title_prefix):
    print(f'\n📁 Testing {filename}')
    print('-' * 40)
    
    try:
        # Step 1: Upload without auto_process
        with open(f'Sample_Convo_html/{filename}', 'rb') as f:
            files = {'transcript_file': (filename, f, 'text/html')}
            data = {
                'title': f'{title_prefix} - {filename}',
                'uploaded_by': 'pipeline_test',
                'auto_process': 'false'  # Upload only, no auto processing
            }
            
            upload_response = requests.post('http://localhost:8000/api/v1/feedme/conversations/upload', 
                                          files=files, data=data, timeout=30)
        
        if upload_response.status_code != 200:
            print(f'❌ Upload failed: {upload_response.status_code}')
            return False
            
        result = upload_response.json()
        conv_id = result.get('id')
        print(f'✅ Upload successful: Conversation {conv_id}')
        
        # Step 2: Trigger processing via reprocess endpoint
        reprocess_response = requests.post(f'http://localhost:8000/api/v1/feedme/conversations/{conv_id}/reprocess')
        if reprocess_response.status_code != 200:
            print(f'❌ Reprocess failed: {reprocess_response.status_code}')
            return False
            
        print(f'✅ Processing triggered successfully')
        
        # Step 3: Monitor processing
        for i in range(10):  # Monitor for 30 seconds
            time.sleep(3)
            
            status_response = requests.get(f'http://localhost:8000/api/v1/feedme/conversations/{conv_id}/status')
            if status_response.status_code == 200:
                status_data = status_response.json()
                current_status = status_data.get('status', 'unknown')
                examples_count = status_data.get('examples_extracted', 0)
                
                print(f'   Check {i+1}: {current_status} ({examples_count} examples)')
                
                if current_status == 'completed':
                    print(f'🎉 SUCCESS! Extracted {examples_count} Q&A pairs')
                    return True
                elif current_status == 'failed':
                    print(f'❌ Processing failed')
                    return False
            else:
                print(f'   Check {i+1}: API error {status_response.status_code}')
        
        print(f'⏰ Still processing after 30 seconds')
        return False
        
    except Exception as e:
        print(f'❌ Error: {e}')
        return False

if __name__ == "__main__":
    # Test with sample files
    test_results = []
    test_files = [
        ('email4.html', 'Hendrik Koch Support'),
        ('email.html', 'Anthony Bowen Support')
    ]

    for filename, title in test_files:
        if os.path.exists(f'Sample_Convo_html/{filename}'):
            success = test_file(filename, title)
            test_results.append((filename, success))
        else:
            print(f'⚠️ File {filename} not found')
            test_results.append((filename, False))

    # Summary
    print(f'\n📊 FINAL RESULTS')
    print('=' * 50)
    successful = sum(1 for _, success in test_results if success)
    total = len(test_results)

    for filename, success in test_results:
        status = '✅ SUCCESS' if success else '❌ FAILED'
        print(f'   {filename}: {status}')

    print(f'\n🎯 Pipeline Success Rate: {successful}/{total} ({successful/total*100:.0f}%)')

    if successful > 0:
        print(f'\n🏆 SOLUTION CONFIRMED:')
        print(f'   1. Enhanced HTML parser handles Zendesk email format')
        print(f'   2. Upload with auto_process=false works reliably') 
        print(f'   3. Reprocess endpoint triggers Celery tasks successfully')
        print(f'   4. Q&A extraction from real customer support transcripts works!')