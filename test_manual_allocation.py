import re
from playwright.sync_api import Page, expect

def test_manual_allocation(page: Page):
    # Go to the application
    page.goto("http://localhost:8000/")
    
    # Wait for data to load
    page.wait_for_selector(".resource-type-row")
    
    # Expand Ambulances drilldown
    ambulance_row = page.locator(".resource-type-row[data-type='ambulance']")
    ambulance_row.click()
    
    # Wait for drilldown to expand
    page.wait_for_selector("#drilldown-ambulance .resource-unit-row")
    
    # Find unit A02
    a02_row = page.locator("#drilldown-ambulance .resource-unit-row", has_text="A02")
    
    # Ensure toggle button exists
    toggle_btn = a02_row.locator(".unit-toggle-btn")
    expect(toggle_btn).to_be_visible()
    
    # Get current state from button text
    initial_text = toggle_btn.inner_text()
    
    # Click to toggle status
    toggle_btn.click()
    
    # Wait for the network patch to complete and state to refresh
    # The toggle button text should change
    if initial_text == "Down":
        expect(toggle_btn).to_have_text("Restore")
    else:
        expect(toggle_btn).to_have_text("Down")
        
    print("Toggle button successfully updated!")
