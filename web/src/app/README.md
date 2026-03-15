Your task: build a NextJS app on https://localhost:3000

- use pnpm as package manager

# Upload Screen, Main page

- Blank page with an Upload File area and button Upload
- The user can upload a mp4 video (FYI, it's a scrollable screencast video of ios screen recording of some existing app)
- The NextJS backend calls a REST endpoint /upload and uploads the video ($input), provides the path to the plan directory ($output)
- Do not build that /upload endpoint yet, assuming it's an external URL
- Transitions to the next screen

# Status Monitoring Screen

- On this screen, the site calls /result REST endpoint every 0.5 seconds, expects { status: "pending", message: string } and prints the message
- Once the status returned changed to { status: "finished", plan: string, imageUrls: string[] }, the app switches to Chat screen. Here, `imageUrls` are screenshots extracted from the video (screens of the original app), and `plan` is the description of each screenshot.

# Chat screen

## Left sidebar 1

- 25% width
- history of chat messages (75% height, scrollable, scrolling to the bottom by default), the 1st message is what was returned in `plan`
- below it, a textarea 25% height (to allow entering a new message) and Send button
- When the user clicks Send, the backend calls /write-code REST endpoint that accepts $messages (previous chat messages + newly entered message from the textarea). The just-written message is appended to the chat history
- When the user clicks Send again, a /write-code REST endpoint is called again

## Left sidebar 2

- 25% width
- List of screenshot images from $imageUrls, vertically located, with scrolling

## Main area

- 50% width
- An IFRAME (50% width, 100% height) that points to https://localhost:3040
