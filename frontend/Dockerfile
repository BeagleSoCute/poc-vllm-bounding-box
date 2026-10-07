# เซิร์ฟเวอร์ dev ของ Vite (hot reload)
# โค้ดไม่ได้ถูกคัดลอกเข้าอิมเมจ แต่ผูกโฟลเดอร์ frontend ของเครื่องเข้ามาใน docker-compose.yml
FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
