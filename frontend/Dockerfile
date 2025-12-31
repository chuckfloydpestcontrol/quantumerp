FROM node:20-alpine

WORKDIR /app

# Copy package files and install dependencies
# This layer is cached unless package.json or package-lock.json changes
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source code (separate layer for better caching)
COPY . .

# Expose port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev"]
