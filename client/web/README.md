# Maps Agentic UI Toolkit Web Client Library

![Alpha](https://img.shields.io/badge/release-alpha-orange)
[![Python CI](https://github.com/googlemaps/a2ui/actions/workflows/python-ci.yml/badge.svg)](https://github.com/googlemaps/a2ui/actions/workflows/python-ci.yml)
[![Web CI](https://github.com/googlemaps/a2ui/actions/workflows/web-ci.yml/badge.svg)](https://github.com/googlemaps/a2ui/actions/workflows/web-ci.yml)
[![GitHub License](https://img.shields.io/github/license/googlemaps/a2ui?color=blue&v=1)](https://github.com/googlemaps/a2ui/blob/main/LICENSE)
[![npm](https://img.shields.io/npm/v/@googlemaps/a2ui)](https://npmjs.com/package/@googlemaps/a2ui)

This package provides the Web (Lit-based) client library for the Maps Agentic UI
Toolkit (MAUI). It includes components and utilities to render A2UI surfaces and
communicate with an A2A agent server.

Note: This library only works when paired with an Agent that can generate A2UI. See [Agentic UI Toolkit samples](https://github.com/googlemaps-samples/a2ui) for a reference implementation of an A2A Agent.

## How to Integrate

To integrate these components into an existing application, you can refer to the [Agentic UI Toolkit samples project](https://github.com/googlemaps-samples/a2ui).

### 1. Install

```bash
npm i @googlemaps/a2ui
```

### 2. Import and Use
In your application code (e.g., a React component):

```tsx
import { A2UIClient, A2UIRenderer, themeStyleSheet } from '@googlemaps/a2ui/lit';

// 1. Adopt the theme stylesheet globally
document.adoptedStyleSheets = [...document.adoptedStyleSheets, themeStyleSheet];

// 2. Initialize client and renderer
const client = new A2UIClient("http://localhost:10002");
const renderer = new A2UIRenderer();

// 3. Add message handling
async function handleSend(messageText: string) {
    renderer.addUserMessage(messageText)

    // 1. Send the message to the A2A agent via A2UIClient
    const response = await client.send(messageText)

    // 2. Process the response (which may contain text and/or A2UI data)
    renderer.processResponse(response);
  }

// 4. Render surfaces in your HTML/JSX

return (
  // Note: <maui-providers> should wrap the area to provide markdown context
  <maui-providers>
    {for (const timelineItem of renderer.timeline) {
    if (timelineItem.type === 'user') {
      return (
        <div className="user-message">
          {timelineItem.text}
        </div>
      )
    } else if (timelineItem.type === 'surface') {
      // Render an A2UI Surface containing multiple UI components
      const surface = renderer.getSurface(timelineItem.surfaceId)
      if (!surface) return null;
      return (
        <div class="surface-message">
          <a2ui-surface
            surface={surface}
          ></a2ui-surface>
        </div>
      ); 
    }
    }}
  </maui-providers>
);
```

## Local Development

To make changes to this package and test them in an application:

### 1. Build and Prepare the Package

To build the package for use in an application:

1.  Open this directory in a terminal.
2.  Install dependencies and link:
    ```bash
    npm run build-and-link
    ```


### 2. Link the Package
You can consume the package via npm linking for local development:
```bash
# In your application directory
npm link @googlemaps/a2ui
```