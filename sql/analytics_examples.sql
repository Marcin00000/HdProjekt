-- Zapytania analityczne — hurtownia job salary (Azure SQL)

-- 1. Lokalizacja z najwyzsza srednia pensja (analog: godzina z najwieksza liczba kursow)
SELECT TOP 5
    j.location,
    COUNT(*) AS job_count,
    AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
FROM fact_salaries f
JOIN dim_job j ON f.job_id = j.job_id
GROUP BY j.location
ORDER BY avg_salary DESC;

-- 2. Srednia pensja wg poziomu wyksztalcenia (analog: srednia odleglosc wg dnia tygodnia)
SELECT
    j.education_level,
    COUNT(*) AS job_count,
    AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary,
    MIN(f.salary_amount) AS min_salary,
    MAX(f.salary_amount) AS max_salary
FROM fact_salaries f
JOIN dim_job j ON f.job_id = j.job_id
GROUP BY j.education_level
ORDER BY avg_salary DESC;

-- 3. Branza z najwyzszym lacznym wynagrodzeniem (analog: vendor z najwiekszym przychodem)
SELECT TOP 5
    c.industry,
    c.company_size,
    COUNT(*) AS job_count,
    SUM(CAST(f.salary_amount AS BIGINT)) AS total_salary,
    AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
FROM fact_salaries f
JOIN dim_company c ON f.company_id = c.company_id
GROUP BY c.industry, c.company_size
ORDER BY total_salary DESC;

-- 4. Praca zdalna vs pensja
SELECT
    j.remote_work,
    COUNT(*) AS job_count,
    AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
FROM fact_salaries f
JOIN dim_job j ON f.job_id = j.job_id
GROUP BY j.remote_work
ORDER BY avg_salary DESC;
