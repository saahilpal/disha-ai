FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv

COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY . /srv/disha_core

RUN useradd --system --uid 10001 --create-home disha
USER 10001
EXPOSE 8000
CMD ["uvicorn", "disha_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
