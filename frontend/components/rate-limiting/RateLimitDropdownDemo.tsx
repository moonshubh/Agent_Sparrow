'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { RateLimitDropdown } from './RateLimitDropdown';

/**
 * Demo component to showcase the new RateLimitDropdown
 * This demonstrates the improved positioning and collapsible behavior
 */
export const RateLimitDropdownDemo: React.FC = () => {
  return (
    <div className="space-y-6 p-6">
      <Card>
        <CardHeader>
          <CardTitle>Rate Limit UI Improvement</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-gray-600">
            <p><strong>Problem:</strong> Rate limits card was too close to browser top bar (cramped appearance)</p>
            <p><strong>Solution:</strong> Collapsible dropdown positioned next to FeedMe icon</p>
          </div>

          <div className="border rounded-lg p-4 bg-gray-50">
            <h3 className="text-sm font-medium mb-3">New Header Layout Preview</h3>
            <div className="flex items-center justify-between bg-white border rounded p-2">
              <div className="text-sm font-semibold text-blue-600">
                MB-Sparrow
              </div>
              <div className="flex items-center gap-3">
                {/* Rate Limit Dropdown */}
                <RateLimitDropdown autoUpdate={false} />
                
                {/* FeedMe Button (simulated) */}
                <button className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200">
                  📁 FeedMe
                </button>
                
                {/* Theme Toggle (simulated) */}
                <button className="p-1 rounded hover:bg-gray-100">
                  🌙
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-medium">Key Features:</h3>
            <ul className="text-xs text-gray-600 space-y-1">
              <li>✅ <strong>Collapsible:</strong> Click to open/close rate limit details</li>
              <li>✅ <strong>Auto-close:</strong> Automatically closes after 10 seconds</li>
              <li>✅ <strong>Click-outside:</strong> Closes when clicking elsewhere</li>
              <li>✅ <strong>Status indicator:</strong> Icon changes based on system health</li>
              <li>✅ <strong>Clean positioning:</strong> Next to FeedMe icon, away from browser top</li>
              <li>✅ <strong>Space efficient:</strong> Minimal footprint when closed</li>
            </ul>
          </div>

          <div className="text-xs text-gray-500 border-t pt-3">
            <strong>Before:</strong> Permanent 264px wide card taking header space<br/>
            <strong>After:</strong> Small button (auto-expanding on click) with rich dropdown content
          </div>
        </CardContent>
      </Card>
    </div>
  );
};