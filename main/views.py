from django.shortcuts import render
from rest_framework.views import APIView
from .serializers import LecturerSerializer,CategorySerializer,CourseSerializer,AssignemtSerializer,StudentSerializer,StudentCourseEnrollmentSerializer#ChapterSerializer
from rest_framework.response import Response
from rest_framework import generics
from rest_framework import permissions #if want to access to data must want cedentials
from . import models
from .models import Lecturer, St_Assignment
from django.core.exceptions import ValidationError
from .utils import calculate_similarity, extract_text_from_file
import json
from django.http import HttpResponseBadRequest, JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .serializers import LecturerSerializer
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from .serializers import EnrollmentVerificationSerializer,CourseDetailSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import FileResponse
from django.views.decorators.http import require_GET
import mimetypes,os
import logging
from django.conf import settings
from .web_similarity import analyze_assignment_web_similarity
import datetime
from django.core.files.storage import FileSystemStorage
from .models import StudentSubmission


#we use generics method to get post and delete functions.when we useprevious method using API view then we have to mension all input Fields

class LecturerList(generics.ListCreateAPIView):
    queryset = models.Lecturer.objects.all()
    serializer_class = LecturerSerializer

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {'error': 'A lecturer with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )


class LecturerDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.Lecturer.objects.all()
    serializer_class = LecturerSerializer
    #permission_classes = [permissions.IsAuthenticated]
 
@csrf_exempt
def lecturer_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not email or not password:
            return JsonResponse({
                'bool': False,
                'message': 'Email and password are required'
            })
        
        try:
            # First try to get the lecturer by email only
            lecturer = models.Lecturer.objects.get(email=email)
            
            # Then verify the password
            if lecturer.password == password:
                return JsonResponse({
                    'bool': True,
                    'lecturer_id': lecturer.id
                })
            else:
                return JsonResponse({
                    'bool': False,
                    'message': 'Invalid password'
                })
                
        except ObjectDoesNotExist:
            return JsonResponse({
                'bool': False,
                'message': 'No lecturer found with this email'
            })
        except Exception as e:
            return JsonResponse({
                'bool': False,
                'message': f'Login error: {str(e)}'
            })
            
    return JsonResponse({
        'bool': False,
        'message': 'Invalid request method'
    })
    
    

class CategoryList(generics.ListCreateAPIView):
    queryset = models.CourseCategory.objects.all()
    serializer_class = CategorySerializer
    #permission_classes = [permissions.IsAuthenticated]

class CourseList(generics.ListCreateAPIView):
    queryset = models.Course.objects.all()
    serializer_class = CourseSerializer
    #permission_classes = [permissions.IsAuthenticated]

class CourseDetail(generics.RetrieveAPIView):
    queryset = models.Course.objects.all()
    serializer_class = CourseSerializer
    
logger = logging.getLogger(__name__)
class VerifyEnrollmentKey(APIView):
    def post(self, request):
        user_type = request.data.get('user_type')
        user_id = request.data.get('user_id')
        course_id = request.data.get('course_id')
        provided_key = request.data.get('enrollment_key')

        logger.info(f"Request data: {request.data}")
        logger.info(f"Course ID provided: {course_id}")
        
        # Check if any key was provided
        if provided_key is None:
            return Response({
                'status': 'error',
                'message': 'No enrollment key provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Convert course_id to int
            course_id = int(course_id)
            
            # Retrieve the course
            course = get_object_or_404(models.Course, id=course_id)
            
            # Retrieve the stored enrollment key
            db_key = course.enrollment_key
            
            # Check if enrollment key exists in the database
            if db_key is None:
                logger.warning(f"No enrollment key set for Course ID {course_id}")
                
                # Check if the course requires an enrollment key
                if hasattr(course, 'requires_enrollment_key') and not course.requires_enrollment_key:
                    # If the course doesn't require a key, allow enrollment
                    logger.info(f"Course ID {course_id} doesn't require an enrollment key")
                    return Response({
                        'status': 'success',
                        'message': 'Enrollment key not required for this course'
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'status': 'error',
                        'message': 'No enrollment key set for this course'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Normalize keys for comparison - convert to string, strip whitespace
            if db_key is not None:
                db_key_str = str(db_key).strip()
            else:
                db_key_str = ""
                
            if provided_key is not None:
                provided_key_str = str(provided_key).strip()
            else:
                provided_key_str = ""
            
            # Log normalized keys for debugging
            logger.info(f"Normalized database key: '{db_key_str}', length: {len(db_key_str)}")
            logger.info(f"Normalized provided key: '{provided_key_str}', length: {len(provided_key_str)}")
            
            # Simple equality check with normalized strings
            if db_key_str == provided_key_str:
                logger.info(f"Valid enrollment key for Course ID {course_id}")
                return Response({
                    'status': 'success',
                    'message': 'Enrollment key verified successfully'
                }, status=status.HTTP_200_OK)
            
            # If still no match, try lowercase comparison as fallback
            if db_key_str.lower() == provided_key_str.lower():
                logger.info(f"Valid enrollment key (case-insensitive) for Course ID {course_id}")
                return Response({
                    'status': 'success',
                    'message': 'Enrollment key verified successfully'
                }, status=status.HTTP_200_OK)
                
            # If all comparison attempts fail
            logger.warning(f"Incorrect enrollment key provided for Course ID {course_id}")
            return Response({
                'status': 'error',
                'message': 'Invalid enrollment key'
            }, status=status.HTTP_400_BAD_REQUEST)

        except ObjectDoesNotExist:
            logger.warning(f"No course found for Course ID {course_id}")
            return Response({
                'status': 'error',
                'message': 'No course found for the provided ID'
            }, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            logger.error(f"ValueError: {e}")
            return Response({
                'status': 'error',
                'message': 'Invalid course ID format'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
            
class CourseEnrolledStudentList(APIView):
    def get(self, request, course_id):
        try:
            enrollments = models.StudentCourseEnrollment.objects.filter(
                course_id=course_id
            ).select_related('student')
            
            # Get the student objects from enrollments
            students = [enrollment.student for enrollment in enrollments]
            serializer = StudentSerializer(
                students, 
                many=True,
                context={'course_id': course_id}
            )
            return Response(serializer.data)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
            
class CourseEnrollmentCount(APIView):
    def get(self, request, course_id):
        try:
            # Count enrollments for this specific course
            count = models.StudentCourseEnrollment.objects.filter(
                course_id=course_id
            ).count()
            
            return Response({
                'status': 'success',
                'count': count
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

# Add this to your views.py
class CourseAssignmentList(generics.ListAPIView):
    serializer_class = AssignemtSerializer

    def get_queryset(self):
        course_id = self.kwargs['course_id']
        return models.Assignment.objects.filter(course_id=course_id).order_by('-uploaded_at')

#Lecturer Assignment
class AssignmentList(generics.ListCreateAPIView):
    
    queryset = models.Assignment.objects.all()
    serializer_class = AssignemtSerializer
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
        try:
            # Validate file size
            if request.FILES.get('file').size > 10 * 1024 * 1024:  # 10MB limit
                return Response(
                    {'message': 'File size should not exceed 10MB'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
                headers=headers
            )
        except Exception as e:
            return Response(
                {'message': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
            # delete assignments
    def get(self, request, course_id, assignment_id):
        """
        Retrieve a specific assignment
        """
        assignment = get_object_or_404(models.Assignment, id=assignment_id, course_id=course_id)
        serializer = AssignemtSerializer(assignment)
        return Response(serializer.data)
    
    def put(self, request, course_id, assignment_id):
        """
        Update a specific assignment
        """
        assignment = get_object_or_404(models.Assignment, id=assignment_id, course_id=course_id)
        serializer = AssignemtSerializer(assignment, data=request.data, partial=True)
        
        if serializer.is_valid():
            # If a new file is being uploaded and there's an existing file, delete the old one
            if 'file' in request.FILES and assignment.file:
                try:
                    old_file_path = assignment.file.path
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old file: {e}")
            
            serializer.save()
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, course_id, assignment_id):
        """
        Delete a specific assignment
        """
        assignment = get_object_or_404(models.Assignment, id=assignment_id, course_id=course_id)
        
        # Delete the file from storage if it exists
        if assignment.file:
            try:
                file_path = assignment.file.path
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file: {e}")
        
        # Delete the assignment record
        assignment.delete()
        
        return Response({"message": "Assignment deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
@require_GET
def download_assignment(request, assignment_id):
    assignment = get_object_or_404( id=assignment_id)
    
    try:
        # Get the full path of the file
        file_path = assignment.file.path
        
        # Determine the correct MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = 'application/octet-stream'
        
        # Get the original filename
        filename = os.path.basename(file_path)
        
        # Open the file in binary mode
        with open(file_path, 'rb') as file:
            response = HttpResponse(
                file.read(), 
                content_type=mime_type
            )
            
            # Set Content-Disposition to force download with original filename
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    
    except Exception as e:
        print(f"Download error: {e}")
        return HttpResponseBadRequest('File could not be downloaded')
    
    

# specific Lecturer course
class LecturerCourseList(generics.ListAPIView):
    serializer_class = CourseSerializer
    #permission_classes = [permissions.IsAuthenticated]

   

    def get_queryset(self):
        lecturer_id = self.kwargs.get('lecturer_id')
        if not lecturer_id:
            return Response({'error': 'Lecturer ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        return models.Course.objects.filter(lecturer_id=lecturer_id)

    
#Similarity checker Assignments
@csrf_exempt
def upload_assignment(request):
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            file = request.FILES.get('file')
            
            if not title or not file:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Both title and file are required'
                }, status=400)
            
            # Validate file extension
            allowed_extensions = ['txt', 'doc', 'docx', 'pdf']
            file_extension = file.name.split('.')[-1].lower()
            if file_extension not in allowed_extensions:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid file type. Allowed types: {", ".join(allowed_extensions)}'
                }, status=400)
            
            # Validate file size (10MB limit)
            if file.size > 10 * 1024 * 1024:
                return JsonResponse({
                    'status': 'error',
                    'message': 'File size should not exceed 10MB'
                }, status=400)
            
            assignment = St_Assignment.objects.create(title=title, file=file)
            
            return JsonResponse({
                'status': 'success',
                'assignment_id': assignment.id,
                'title': assignment.title,
                'file_url': assignment.file.url if assignment.file else None,
                'uploaded_at': assignment.uploaded_At.isoformat() if hasattr(assignment, 'uploaded_At') else None
            })
            
        except ValidationError as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'An unexpected error occurred: {str(e)}'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


@csrf_exempt
def compare_submissions(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            submission_ids = data.get('assignment_ids', [])  # Keep parameter name compatible with frontend
            
            if len(submission_ids) < 2:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please select at least 2 submissions to compare'
                }, status=400)
            
            # Get the submissions with these IDs
            submissions = list(StudentSubmission.objects.filter(id__in=submission_ids))
            
            # Make sure we found enough submissions
            if len(submissions) < 2:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Could not find enough submissions to compare'
                }, status=404)
            
            results = []
            
            # Compare each pair of submissions
            for i in range(len(submissions)):
                for j in range(i + 1, len(submissions)):
                    try:
                        # Get the file paths
                        file_path1 = os.path.join(settings.MEDIA_ROOT, submissions[i].file_path)
                        file_path2 = os.path.join(settings.MEDIA_ROOT, submissions[j].file_path)
                        
                        # Calculate similarity between the files
                        similarity_result = calculate_similarity(file_path1, file_path2)
                        
                        # Build result object
                        result = {
                            'assignment1_id': submissions[i].id,
                            'assignment1_title': f"Submission: {submissions[i].student_name}",
                            'assignment2_id': submissions[j].id,
                            'assignment2_title': f"Submission: {submissions[j].student_name}",
                            'similarity_score': similarity_result.get('similarity_score', 0),
                        }
                        
                        # Add report path if available
                        if similarity_result.get('report_path'):
                            report_filename = os.path.basename(similarity_result['report_path'])
                            result.update({
                                'report_url': f'/api/reports/{report_filename}',
                                'download_url': f'/api/download-report/{report_filename}',
                                'report_filename': report_filename
                            })
                        
                        # Add error if present
                        if 'error' in similarity_result:
                            result['error'] = similarity_result['error']
                            
                        results.append(result)
                    except Exception as e:
                        results.append({
                            'assignment1_id': submissions[i].id,
                            'assignment1_title': f"Submission: {submissions[i].student_name}",
                            'assignment2_id': submissions[j].id,
                            'assignment2_title': f"Submission: {submissions[j].student_name}",
                            'error': f'Failed to compare: {str(e)}',
                            'similarity_score': None
                        })
            
            return JsonResponse({
                'status': 'success',
                'results': results
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Server error: {str(e)}'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

def get_assignments(request):
    if request.method == 'GET':
        try:
            assignments = St_Assignment.objects.all().order_by('-uploaded_At')
            
            # Sort by date from newest to oldest
            assignments_data = []
            for assignment in assignments:
                assignment_data = {
                    'id': assignment.id,
                    'title': assignment.title,
                    'file_url': assignment.file.url if assignment.file else None,
                }
                
                # Add uploaded_at if available
                if hasattr(assignment, 'uploaded_At'):
                    assignment_data['uploaded_at'] = assignment.uploaded_At.isoformat()
                
                assignments_data.append(assignment_data)
            
            return JsonResponse({
                'status': 'success',
                'assignments': assignments_data
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error retrieving assignments: {str(e)}'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

def serve_report(request, filename):
    """Serve a similarity report PDF with improved error handling."""
    try:
        file_path = os.path.join(settings.SIMILARITY_REPORTS_DIR, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        else:
            return HttpResponse('Report file not found', status=404)
    except Exception as e:
        return HttpResponse(f'Error serving report: {str(e)}', status=500)

def download_report(request, filename):
    """Download a similarity report PDF with improved handling."""
    try:
        file_path = os.path.join(settings.SIMILARITY_REPORTS_DIR, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            return HttpResponse('Report file not found', status=404)
    except Exception as e:
        return HttpResponse(f'Error downloading report: {str(e)}', status=500)

# Add this new endpoint to list all available reports
def list_reports(request):
    """List all available similarity reports."""
    try:
        reports_dir = settings.SIMILARITY_REPORTS_DIR
        if not os.path.exists(reports_dir):
            return JsonResponse({
                'status': 'success',
                'reports': []
            })
            
        # Get all PDF files in the reports directory
        report_files = [f for f in os.listdir(reports_dir) if f.endswith('.pdf')]
        
        # Get file details
        reports = []
        for filename in report_files:
            file_path = os.path.join(reports_dir, filename)
            file_stats = os.stat(file_path)
            
            reports.append({
                'filename': filename,
                'size': file_stats.st_size,
                'created': file_stats.st_ctime,
                'view_url': f'/api/reports/{filename}',
                'download_url': f'/api/download-report/{filename}'
            })
            
        # Sort by creation time (newest first)
        reports.sort(key=lambda x: x['created'], reverse=True)
        
        return JsonResponse({
            'status': 'success',
            'reports': reports
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error listing reports: {str(e)}'
        }, status=500)

# Add this new endpoint to delete a report
@csrf_exempt
def delete_report(request, filename):
    """Delete a specific similarity report."""
    if request.method != 'DELETE':
        return JsonResponse({
            'status': 'error',
            'message': 'Method not allowed'
        }, status=405)
        
    try:
        file_path = os.path.join(settings.SIMILARITY_REPORTS_DIR, filename)
        if not os.path.exists(file_path):
            return JsonResponse({
                'status': 'error',
                'message': 'Report not found'
            }, status=404)
            
        # Delete the file
        os.remove(file_path)
        
        return JsonResponse({
            'status': 'success',
            'message': f'Report {filename} deleted successfully'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error deleting report: {str(e)}'
        }, status=500)
        
@csrf_exempt
def check_web_similarity(request):
    """
    Check a student submission against web content for similarity using CrewAI agents.
    
    POST parameters:
    - submission_id: ID of the student submission to check
    
    Returns:
    - JSON response with analysis results and report path
    """
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Only POST method is allowed'
        }, status=405)
    
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')  # Changed from assignment_id to submission_id
        
        if not submission_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Submission ID is required'  # Updated error message
            }, status=400)
        
        # Get the submission instead of assignment
        try:
            submission = StudentSubmission.objects.get(id=submission_id)
        except StudentSubmission.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Submission with ID {submission_id} not found'
            }, status=404)
        
        # Get assignment related to this submission
        assignment = submission.assignment
        
        # Get submission file path using the helper method
        submission_path = submission.get_absolute_file_path()
        
        # Define output directory for reports
        web_reports_dir = os.path.join(settings.SIMILARITY_REPORTS_DIR, 'web_reports')
        os.makedirs(web_reports_dir, exist_ok=True)
        
        logger.info(f"Starting web similarity analysis for submission {submission_id} for assignment {assignment.id}")
        
        # Analyze web similarity using CrewAI
        result = analyze_assignment_web_similarity(submission_path, web_reports_dir)
        
        if 'error' in result:
            logger.error(f"Web similarity analysis failed: {result['error']}")
            return JsonResponse({
                'status': 'error',
                'message': result['error']
            }, status=500)
        
        # Update the similarity score in the database
        submission.similarity_score = result['web_similarity_score']
        submission.save()
        
        # Return success response
        report_filename = os.path.basename(result['report_path'])
        
        logger.info(f"Web similarity analysis completed for submission {submission_id}")
        
        return JsonResponse({
            'status': 'success',
            'submission_id': submission_id,
            'student_name': submission.student_name,
            'assignment_id': assignment.id,
            'assignment_title': assignment.title,
            'web_similarity_score': result['web_similarity_score'],
            'analysis_summary': result['analysis_summary'],
            'report_url': f'/api/web-reports/{report_filename}',
            'download_url': f'/api/download-web-report/{report_filename}'
        })
        
    except Exception as e:
        logger.exception(f"Unexpected error in web similarity check: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'An unexpected error occurred: {str(e)}'
        }, status=500)

def serve_web_report(request, filename):
    """Serve a web similarity report PDF."""
    web_reports_dir = os.path.join(settings.SIMILARITY_REPORTS_DIR, 'web_reports')
    file_path = os.path.join(web_reports_dir, filename)
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(open(file_path, 'rb'), content_type='application/pdf')
    else:
        return HttpResponse('Report file not found', status=404)

def download_web_report(request, filename):
    """Download a web similarity report PDF."""
    web_reports_dir = os.path.join(settings.SIMILARITY_REPORTS_DIR, 'web_reports')
    file_path = os.path.join(web_reports_dir, filename)
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    else:
        return HttpResponse('Report file not found', status=404)

def list_web_reports(request):
    """List all available web similarity reports."""
    try:
        web_reports_dir = os.path.join(settings.SIMILARITY_REPORTS_DIR, 'web_reports')
        os.makedirs(web_reports_dir, exist_ok=True)
        
        # Get all PDF files in the reports directory
        report_files = [f for f in os.listdir(web_reports_dir) if f.endswith('.pdf')]
        
        # Get file details
        reports = []
        for filename in report_files:
            file_path = os.path.join(web_reports_dir, filename)
            file_stats = os.stat(file_path)
            
            reports.append({
                'filename': filename,
                'size': file_stats.st_size,
                'created': file_stats.st_ctime,
                'view_url': f'/api/web-reports/{filename}',
                'download_url': f'/api/download-web-report/{filename}'
            })
            
        # Sort by creation time (newest first)
        reports.sort(key=lambda x: x['created'], reverse=True)
        
        return JsonResponse({
            'status': 'success',
            'reports': reports
        })
    except Exception as e:
        logger.exception(f"Error listing web reports: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error listing web reports: {str(e)}'
        }, status=500)

@csrf_exempt
def delete_web_report(request, filename):
    """Delete a specific web similarity report."""
    if request.method != 'DELETE':
        return JsonResponse({
            'status': 'error',
            'message': 'Method not allowed'
        }, status=405)
        
    try:
        web_reports_dir = os.path.join(settings.SIMILARITY_REPORTS_DIR, 'web_reports')
        file_path = os.path.join(web_reports_dir, filename)
        
        if not os.path.exists(file_path):
            return JsonResponse({
                'status': 'error',
                'message': 'Report not found'
            }, status=404)
            
        # Delete the file
        os.remove(file_path)
        logger.info(f"Deleted web similarity report: {filename}")
        
        return JsonResponse({
            'status': 'success',
            'message': f'Report {filename} deleted successfully'
        })
    except Exception as e:
        logger.exception(f"Error deleting report: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error deleting report: {str(e)}'
        }, status=500)
        
        
#Student submissions
@csrf_exempt
def submit_assignment(request,assignment_id):
    """
    Handle student assignment submission with organized folder structure by assignment ID.
    Also tracks submissions in the database.
    
    POST parameters:
    - assignment_id: ID of the assignment to submit to
    - name: Student name
    - file: Uploaded assignment file
    
    Returns:
    - JSON response with submission status and details
    """
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Only POST method is allowed'
        }, status=405)
    
    try:
        # Get assignment_id, student name and file
        assignment_id = request.POST.get('assignment_id')
        name = request.POST.get('name')
        file = request.FILES.get('file')
        
        # Validate required fields
        if not assignment_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Assignment ID is required'
            }, status=400)
            
        if not name:
            return JsonResponse({
                'status': 'error',
                'message': 'Student name is required'
            }, status=400)
            
        if not file:
            return JsonResponse({
                'status': 'error',
                'message': 'Assignment file is required'
            }, status=400)
        
        # Check if the assignment exists
        try:
            assignment = St_Assignment.objects.get(id=assignment_id)
        except St_Assignment.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Assignment with ID {assignment_id} not found'
            }, status=404)
        
        # Create a folder structure for this assignment
        submissions_base = os.path.join(settings.MEDIA_ROOT, 'student_submissions')
        assignment_dir = os.path.join(submissions_base, f'assignment_{assignment_id}')
        
        # Create directories if they don't exist
        os.makedirs(assignment_dir, exist_ok=True)
        
        # Generate a filename for the student submission
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        safe_name = name.replace(' ', '_')
        filename = f"{safe_name}_{timestamp}{os.path.splitext(file.name)[1]}"
        
        # Save the file to the assignment-specific directory
        fs = FileSystemStorage(location=assignment_dir)
        saved_filename = fs.save(filename, file)
        
        # Build the relative path for accessing the file
        relative_path = os.path.join('student_submissions', f'assignment_{assignment_id}', saved_filename)
        
        # Update or create database record
        try:
            # Check if this student already has a submission for this assignment
            submission, created = StudentSubmission.objects.update_or_create(
                assignment=assignment,
                student_name=name,
                defaults={
                    'file_path': relative_path,
                    'file_name': saved_filename
                }
            )
            
            # Set the submission date for display
            submission_date = submission.submission_date.strftime('%Y-%m-%d %H:%M:%S')
            
            return JsonResponse({
                'status': 'success',
                'message': 'Assignment submitted successfully',
                'data': {
                    'submission_id': submission.id,
                    'assignment_id': assignment_id,
                    'assignment_title': assignment.title,
                    'student_name': name,
                    'file_name': saved_filename,
                    'file_path': relative_path,
                    'file_url': request.build_absolute_uri(settings.MEDIA_URL + relative_path),
                    'submitted_at': submission_date
                }
            })
        except Exception as db_error:
            # If database record fails, still return success but log the error
            # The file is already saved, so the submission is technically successful
            print(f"Error creating database record: {str(db_error)}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Assignment submitted successfully, but there was an issue with the database record',
                'data': {
                    'assignment_id': assignment_id,
                    'assignment_title': assignment.title,
                    'student_name': name,
                    'file_name': saved_filename,
                    'file_path': relative_path,
                    'submitted_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)
        
def delete_submission_handler(request, submission_id):
    """
    Handler for deleting a submission.
    This is called from the submit_assignment view when a deletion action is detected.
    
    Parameters:
    - request: The request object
    - submission_id: ID of the submission to delete
    
    Returns:
    - JSON response with deletion status
    """
    try:
        # Find the submission
        try:
            submission = StudentSubmission.objects.get(id=submission_id)
        except StudentSubmission.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Submission with ID {submission_id} not found'
            }, status=404)
        
        # Get the file path
        file_path = os.path.join(settings.MEDIA_ROOT, submission.file_path)
        
        # Delete the file if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as file_error:
                print(f"Error deleting file: {str(file_error)}")
                # Continue with deletion even if file removal fails
        
        # Check if there are any web similarity reports for this submission
        # Assuming there's a field or relation that connects reports to submissions
        # You may need to adjust this based on your actual model structure
        try:
            from .models import WebSimilarityReport
            reports = WebSimilarityReport.objects.filter(submission_id=submission_id)
            for report in reports:
                # Delete the report file if it exists
                if report.report_path and os.path.exists(os.path.join(settings.MEDIA_ROOT, report.report_path)):
                    os.remove(os.path.join(settings.MEDIA_ROOT, report.report_path))
                # Delete the report record
                report.delete()
        except (ImportError, AttributeError):
            # WebSimilarityReport model might not exist or doesn't have the expected structure
            pass
        
        # Delete the submission record
        submission.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Submission deleted successfully'
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred while deleting the submission: {str(e)}'
        }, status=500)

def list_assignment_submissions(request, assignment_id):
    """
    List all submissions for a specific assignment ID.
    Uses the database records for better performance and data consistency.
    
    Parameters:
    - assignment_id: ID of the assignment
    
    Returns:
    - JSON response with list of submissions
    """
    if request.method != 'GET':
        return JsonResponse({
            'status': 'error',
            'message': 'Only GET method is allowed'
        }, status=405)
        
    try:
        # Check if the assignment exists
        try:
            assignment = St_Assignment.objects.get(id=assignment_id)
        except St_Assignment.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Assignment with ID {assignment_id} not found'
            }, status=404)
        
        # Get all submissions for this assignment from the database
        submissions = StudentSubmission.objects.filter(assignment_id=assignment_id).order_by('-submission_date')
        
        # Format submissions for response
        submissions_data = []
        for submission in submissions:
            submissions_data.append({
                'submission_id': submission.id,
                'student_name': submission.student_name,
                'file_name': submission.file_name,
                'file_path': submission.file_path,
                'file_url': request.build_absolute_uri(settings.MEDIA_URL + submission.file_path),
                'submitted_at': submission.submission_date.strftime('%Y-%m-%d %H:%M:%S'),
                'similarity_score': submission.similarity_score
            })
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'assignment_id': assignment_id,
                'assignment_title': assignment.title,
                'submissions_count': len(submissions_data),
                'submissions': submissions_data
            }
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)
        
@csrf_exempt
def delete_submission(request, submission_id=None):
    """
    Dedicated endpoint for deleting a submission.
    
    Parameters:
    - submission_id: ID of the submission to delete (from URL)
    
    Returns:
    - JSON response with deletion status
    """
    if request.method != 'DELETE':
        # Check if this is a JSON POST request with action=delete
        if request.method == 'POST' and request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                if data.get('action') == 'delete':
                    # Use submission_id from JSON payload if not in URL
                    sid = submission_id or data.get('submission_id')
                    if sid:
                        return delete_submission_handler(request, sid)
            except json.JSONDecodeError:
                pass
                
        return JsonResponse({
            'status': 'error',
            'message': 'Only DELETE method is allowed, or POST with action=delete'
        }, status=405)
    
    # If submission_id is not provided in the URL, check if it's in the request body
    if not submission_id and request.body:
        try:
            data = json.loads(request.body)
            submission_id = data.get('submission_id')
        except json.JSONDecodeError:
            pass
    
    if not submission_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Submission ID is required'
        }, status=400)
    
    # Handle the deletion
    return delete_submission_handler(request, submission_id)
    
    try:
        # Check if the assignment exists
        try:
            assignment = St_Assignment.objects.get(id=assignment_id)
        except St_Assignment.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': f'Assignment with ID {assignment_id} not found'
            }, status=404)
        
        # Get all submissions for this assignment from the database
        submissions = StudentSubmission.objects.filter(assignment_id=assignment_id).order_by('-submission_date')
        
        # Format submissions for response
        submissions_data = []
        for submission in submissions:
            submissions_data.append({
                'submission_id': submission.id,
                'student_name': submission.student_name,
                'file_name': submission.file_name,
                'file_path': submission.file_path,
                'file_url': request.build_absolute_uri(settings.MEDIA_URL + submission.file_path),
                'submitted_at': submission.submission_date.strftime('%Y-%m-%d %H:%M:%S'),
                'similarity_score': submission.similarity_score
            })
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'assignment_id': assignment_id,
                'assignment_title': assignment.title,
                'submissions_count': len(submissions_data),
                'submissions': submissions_data
            }
        })
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)
# Student class

class StudentList(generics.ListCreateAPIView):
    queryset = models.Student.objects.all()
    serializer_class = StudentSerializer
    

class StudentDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.Student.objects.all()
    serializer_class = StudentSerializer
    #permission_classes = [permissions.IsAuthenticated]
 

@csrf_exempt  
def  user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        try:
            studentData = models.Student.objects.get(username=username, password=password)
            return JsonResponse({
                'bool': True,
                'student_id': studentData.id
            })
        except models.Student.DoesNotExist:
            return JsonResponse({'bool': False})
    return JsonResponse({'bool': False})

##class ChapterList(generics.ListCreateAPIView):
   # queryset = models.Chapter.objects.all()
    #serializer_class = ChapterSerializer
    #permission_classes = [permissions.IsAuthenticated]


class StudentCourseEnrollmentList(generics.ListCreateAPIView):
    queryset = models.StudentCourseEnrollment.objects.all()
    serializer_class = StudentCourseEnrollmentSerializer


class EnrolledStudentList(generics.ListAPIView):
    serializer_class = CourseSerializer
    
    def get_queryset(self):
        student_id = self.kwargs['student_id']
        student = models.Student.objects.get(pk=student_id)
        return models.Course.objects.filter(
            studentcourseenrollment__student=student
        ).distinct()
        

# Update this function in your Django views.py file
@csrf_exempt
def update_profile_image(request):
    if request.method == 'POST':
        lecturer_id = request.POST.get('lecturer_id')
        profile_image = request.FILES.get('profile_image')
        
        try:
            # Import the Lecturer model
            from .models import Lecturer
            
            lecturer = Lecturer.objects.get(id=lecturer_id)
            
            # Delete old image if it exists
            if lecturer.profile_image:
                try:
                    if os.path.exists(lecturer.profile_image.path):
                        os.remove(lecturer.profile_image.path)
                except Exception as e:
                    print(f"Error removing old image: {e}")
            
            lecturer.profile_image = profile_image
            lecturer.save()
            
            # Construct the full URL to the profile image
            if lecturer.profile_image:
                if request.is_secure():
                    protocol = 'https://'
                else:
                    protocol = 'http://'
                host = request.get_host()
                image_url = protocol + host + lecturer.profile_image.url
            else:
                image_url = None
            
            return JsonResponse({
                'status': 'success',
                'message': 'Profile image updated',
                'image_url': image_url
            })
        except Lecturer.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Lecturer not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error updating image: {str(e)}'
            }, status=500)
    
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=405)
    
@csrf_exempt
def remove_profile_image(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        lecturer_id = data.get('lecturer_id')
        
        try:
            lecturer = Lecturer.objects.get(id=lecturer_id)
            if lecturer.profile_image:
                lecturer.profile_image.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Profile image removed'
            })
        except Lecturer.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Lecturer not found'
            }, status=404)
