class School:
    def __init__(self):
        # Store students as a dict: grade -> set of names
        self._students = {}
        # Track add results
        self._add_results = []

    def add_student(self, name, grade):
        # Check if student already exists in any grade
        for existing_grade in self._students:
            if name in self._students[existing_grade]:
                self._add_results.append(False)
                return False
        
        # Add student to the grade
        if grade not in self._students:
            self._students[grade] = set()
        self._students[grade].add(name)
        self._add_results.append(True)
        return True

    def added(self):
        return self._add_results

    def roster(self):
        # Sort by grade, then by name within each grade
        result = []
        for grade in sorted(self._students.keys()):
            for name in sorted(self._students[grade]):
                result.append(name)
        return result

    def grade(self, grade_number):
        # Return sorted list of students in the specified grade
        if grade_number not in self._students:
            return []
        return sorted(self._students[grade_number])