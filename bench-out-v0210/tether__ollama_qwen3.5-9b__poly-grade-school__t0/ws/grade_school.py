class School:
    def __init__(self):
        # Dictionary to store students by grade
        # Key: grade number, Value: set of student names
        self._students = {}
        # Track add_student results
        self._added_results = []

    def add_student(self, name, grade):
        """Add a student to a grade.
        
        Returns True if student was added, False if student already exists.
        """
        # Check if student already exists in any grade
        for students in self._students.values():
            if name in students:
                self._added_results.append(False)
                return False
        
        # Add student to the grade
        if grade not in self._students:
            self._students[grade] = set()
        
        self._students[grade].add(name)
        self._added_results.append(True)
        return True

    def added(self):
        """Return list of booleans indicating success of each add_student call."""
        return self._added_results

    def roster(self):
        """Return a sorted list of all students.
        
        Sorted by grade first, then by name within each grade.
        """
        result = []
        # Sort grades numerically
        for grade in sorted(self._students.keys()):
            # Get students in this grade and sort alphabetically
            students = sorted(self._students[grade])
            result.extend(students)
        return result

    def grade(self, grade_number):
        """Return a sorted list of students in the specified grade."""
        if grade_number not in self._students:
            return []
        return sorted(self._students[grade_number])