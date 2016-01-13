Reusable apps for cart and checkout functionality. These are intended to be used
as a base and hacked on, per project, rather than being pluggable apps. The
advantage of this is that the code can be customised however needed, and
modified by future devs, without having to consider the general case or have
access to a this repo.


Recommended usage
=================

1. Check out django-shoptools into your project
2. Put the bits you need on your path (i.e. symlink into your src directory,
   or add the django-shoptools directory to your path)
3. Modify as needed, and check the whole lot in to your project repo.
4. If you've made changes which are not specific to the project and have
   general usefulness, selectively commit them to the django-shoptools repo
   and push back upstream
