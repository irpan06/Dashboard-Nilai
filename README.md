# 🎓 Academic Performance Analysis Dashboard

An interactive **Streamlit**-based application for analyzing student transcripts at **Universitas Airlangga (UNAIR)**.  
Key features include calculating **GPA, grade distribution, credit progress**, and **grade simulation**.  

🌐 **Online Demo**: [Try on Streamlit Cloud](https://dashboard-nilai.streamlit.app/)  

---

## ✨ Main Features  
- 🔑 **Login** to automatically retrieve transcripts.  
- 📊 **GPA & Semester GPA visualization** with interactive charts.  
- 📈 **Grade distribution** per semester.  
- 🎯 **Credit progress (mandatory & elective/KBK)** based on UNAIR curriculum.  
- 🧮 **Grade simulation** to predict future GPA.  
- 📋 **List of uncompleted courses** (specific to Physics program at UNAIR).  

---

## 🚀 How to Run Locally  
1. Clone the repository:  
   ```bash
   git clone https://github.com/username/dashboard-nilai-unair.git
   cd dashboard-nilai-unair
   ```  

2. Install dependencies:  
   ```bash
   pip install -r requirements.txt
   ```  

3. Run the application:  
   ```bash
   streamlit run nilai.py
   ```  

---

## 📸 Preview  
Overview Page:  
![overview-gpa](assets/overview-ipk.png)  
![overview-sgpa](assets/overview-ips.png)  

Simulation Page:  
![simulation](assets/simulasi.png)  

---

## 🛠️ Technology & Implementation  

This application is built with the Python stack for data processing, visualization, and automation:  

- **Streamlit** → main framework for building the interactive dashboard.  
- **Pandas** → transcript data processing and GPA/SGPA calculations.  
- **Matplotlib & Plotly** → data visualization (grade distribution, SGPA charts, GPA donut chart).  
- **st-aggrid** → interactive tables for grade simulation.  
- **Requests + BeautifulSoup** → login to UNAIR academic portal & scrape transcript data.  
- **OpenPyXL** → export transcript data to Excel format.  
- **Difflib (SequenceMatcher)** → match course names with UNAIR curriculum.  

**Application flow:**  
1. **Login / Input data** 
2. **Scraping & parsing** → transcript data retrieved using *requests* and processed with *BeautifulSoup*.  
3. **Data processing** → transcript is cleaned, GPA/SGPA calculated, and matched with UNAIR curriculum.  
4. **Visualization** → analysis results displayed in interactive charts and dynamic tables.  
5. **Simulation** → users can adjust grades to predict future GPA.  

---

## ℹ️ Notes  

- This application was originally developed for **Universitas Airlangga**, specifically for the **Physics Program**.  
- Features like *"Uncompleted Courses"* are only applicable to the Physics UNAIR curriculum.  
- However, the curriculum matching logic can be easily adapted for other UNAIR programs or different universities by replacing the curriculum files (e.g., `data/mk_wajib.xlsx`, `data/mk_kbk.xlsx`).  

---

## 👤 Author  
**Muhamad Irvandi – Universitas Airlangga**  
[LinkedIn](https://www.linkedin.com/in/irvandddi/) | [GitHub](https://github.com/irpan06)  
