FROM nginx:alpine
COPY index.html browse.html abs.html about.html /usr/share/nginx/html/
COPY data/ /usr/share/nginx/html/data/
COPY papers/ /usr/share/nginx/html/papers/
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
