# PicoCalc wiki

# 📝 Contributing to the PicoCalc Wiki

Thank you for your interest in contributing to the PicoCalc Wiki!

To keep everything organized and consistent, please follow these guidelines when editing or adding wiki pages.

---

## 📌 Contribution Guidelines

1. **Edit or Create Markdown Files**

   - All wiki pages are written in `.md` format.
   - To contribute, modify an existing `.md` file or create a new one under the `wiki/` directory in the repository.

2. **Naming Convention**

   - Use **hyphens (`-`)** to separate words in filenames.
   - **Do not use spaces** in filenames.

     **✅ Correct:** `Getting-Started.md`  
     **❌ Incorrect:** `Getting Started.md`

3. **Submit a Pull Request**

   - After making your changes, create a pull request (PR) to the `PicoCalc` repository.

4. **Automatic Wiki Update**

   - Once your PR is merged, all files under the `wiki/` directory will be published automatically to the GitHub Wiki at:  
     👉 [https://github.com/clockworkpi/PicoCalc/wiki](https://github.com/clockworkpi/PicoCalc/wiki)

---

## ✅ Example Workflow

```bash
# Clone the repository
fork https://github.com/clockworkpi/PicoCalc.git # fork your own copy of PicoCalc repo


git clone https://github.com/Anonymous/PicoCalc.git
cd PicoCalc

# Create a new branch
git checkout -b update-getting-started

# Edit or add a markdown file under the wiki/ directory
nano wiki/Getting-Started.md

# Stage and commit your changes
git add wiki/Getting-Started.md
git commit -m "Add Getting Started guide"

# Push your changes and open a Pull Request to original PicoCalc.git
git push origin update-getting-started
```

