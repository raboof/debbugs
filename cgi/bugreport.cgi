#!/usr/bin/perl -wT

use warnings;
use strict;

use POSIX qw(strftime);
use MIME::Parser;
use MIME::Decoder;
use IO::Scalar;
use IO::File;

use Debbugs::Config qw(:globals :text);

# for read_log_records
use Debbugs::Log qw(read_log_records);
use Debbugs::CGI qw(:url :html :util);
use Debbugs::CGI::Bugreport qw(:all);
use Debbugs::Common qw(buglog getmaintainers);
use Debbugs::Packages qw(getpkgsrc);
use Debbugs::Status qw(splitpackages get_bug_status isstrongseverity);

use Scalar::Util qw(looks_like_number);

use Debbugs::Text qw(:templates);

use CGI::Simple;
my $q = new CGI::Simple;

my %param = cgi_parameters(query => $q,
			   single => [qw(bug msg att boring terse),
				      qw(reverse mbox mime trim),
				      qw(mboxstat mboxmaint archive),
				      qw(repeatmerged)
				     ],
			   default => {# msg       => '',
				       boring    => 'no',
				       terse     => 'no',
				       reverse   => 'no',
				       mbox      => 'no',
				       mime      => 'no',
				       mboxstat  => 'no',
				       mboxmaint => 'no',
				       archive   => 'no',
				       repeatmerged => 'yes',
				      },
			  );
# This is craptacular.

my $ref = $param{bug} or quitcgi("No bug number");
$ref =~ /(\d+)/ or quitcgi("Invalid bug number");
$ref = $1;
my $short = "#$ref";
my ($msg) = $param{msg} =~ /^(\d+)$/ if exists $param{msg};
my ($att) = $param{att} =~ /^(\d+)$/ if exists $param{att};
my $boring = $param{'boring'} eq 'yes';
my $terse = $param{'terse'} eq 'yes';
my $reverse = $param{'reverse'} eq 'yes';
my $mbox = $param{'mbox'} eq 'yes';
my $mime = $param{'mime'} eq 'yes';

my $trim_headers = ($param{trim} || ((defined $msg and $msg)?'no':'yes')) eq 'yes';

my $mbox_status_message = $param{mboxstat} eq 'yes';
my $mbox_maint = $param{mboxmaint} eq 'yes';
$mbox = 1 if $mbox_status_message or $mbox_maint;


# Not used by this script directly, but fetch these so that pkgurl() and
# friends can propagate them correctly.
my $archive = $param{'archive'} eq 'yes';
my $repeatmerged = $param{'repeatmerged'} eq 'yes';

my $buglog = buglog($ref);
if (not defined $buglog) {
     print $q->header(-status => "404 No such bug",
		      -type => "text/html",
		      -charset => 'utf-8',
		     );
     exit 0;
}

my @stat = stat $buglog;
my $mtime = '';
if (@stat) {
     $mtime = strftime '%a, %d %b %Y %T GMT', gmtime($stat[9]);
}

if ($q->request_method() eq 'HEAD' and not defined($att) and not $mbox) {
     print $q->header(-type => "text/html",
		      -charset => 'utf-8',
		      (length $mtime)?(-last_modified => $mtime):(),
		     );
     exit 0;
}


my $buglogfh;
if ($buglog =~ m/\.gz$/) {
    my $oldpath = $ENV{'PATH'};
    $ENV{'PATH'} = '/bin:/usr/bin';
    $buglogfh = IO::File->new("zcat $buglog |") or quitcgi("open log for $ref: $!");
    $ENV{'PATH'} = $oldpath;
} else {
    $buglogfh = IO::File->new($buglog,'r') or quitcgi("open log for $ref: $!");
}


my %status = %{get_bug_status(bug=>$ref)};

my @records;
eval{
     @records = read_log_records($buglogfh);
};
if ($@) {
     quitcgi("Bad bug log for $gBug $ref. Unable to read records: $@");
}
undef $buglogfh;


my $log='';
my $msg_num = 0;
my $skip_next = 0;
if (defined($msg) and ($msg-1) <= $#records) {
     @records = ($records[$msg-1]);
     $msg_num = $msg - 1;
}
my @log;
if ( $mbox ) {
     my $date = strftime "%a %b %d %T %Y", localtime;
     if (@records > 1) {
	  print qq(Content-Disposition: attachment; filename="bug_${ref}.mbox"\n);
	  print "Content-Type: text/plain\n\n";
     }
     else {
	  $msg_num++;
	  print qq(Content-Disposition: attachment; filename="bug_${ref}_message_${msg_num}.mbox"\n);
	  print "Content-Type: message/rfc822\n\n";
     }
     if ($mbox_status_message and @records > 1) {
	  my $status_message='';
	  my @status_fields = (retitle   => 'subject',
			       package   => 'package',
			       submitter => 'originator',
			       severity  => 'severity',
			       tag       => 'tags',
			       owner     => 'owner',
			       blocks    => 'blocks',
			       forward   => 'forward',
			      );
	  my ($key,$value);
	  while (($key,$value) = splice(@status_fields,0,2)) {
	       if (defined $status{$value} and length $status{$value}) {
		    $status_message .= qq($key $ref $status{$value}\n);
	       }
	  }
	  print STDOUT qq(From unknown $date\n),
	       create_mime_message([From       => "$gBug#$ref <$ref\@$gEmailDomain>",
				    To         => "$gBug#$ref <$ref\@$gEmailDomain>",
				    Subject    => "Status: $status{subject}",
				    "Reply-To" => "$gBug#$ref <$ref\@$gEmailDomain>",
				   ],
				   <<END,);
$status_message
thanks


END
     }
     my $message_number=0;
     my %seen_message_ids;
     for my $record (@records) {
	  next if $record->{type} !~ /^(?:recips|incoming-recv)$/;
	  my $wanted_type = $mbox_maint?'recips':'incoming-recv';
	  # we want to include control messages anyway
	  my $record_wanted_anyway = 0;
	  my ($msg_id) = $record->{text} =~ /^Message-Id:\s+<(.+)>/im;
	  next if exists $seen_message_ids{$msg_id};
	  next if $msg_id =~/handler\..+\.ack(?:info|done)?\@/;
	  $record_wanted_anyway = 1 if $record->{text} =~ /^Received: \(at control\)/;
	  next if not $boring and not $record->{type} eq $wanted_type and not $record_wanted_anyway and @records > 1;
	  $seen_message_ids{$msg_id} = 1;
	  my @lines = split( "\n", $record->{text}, -1 );
	  if ( $lines[ 1 ] =~ m/^From / ) {
	       my $tmp = $lines[ 0 ];
	       $lines[ 0 ] = $lines[ 1 ];
	       $lines[ 1 ] = $tmp;
	  }
	  if ( !( $lines[ 0 ] =~ m/^From / ) ) {
	       unshift @lines, "From unknown $date";
	  }
	  map { s/^(>*From )/>$1/ } @lines[ 1 .. $#lines ];
	  print join( "\n", @lines ) . "\n";
     }
     exit 0;
}

else {
     if (defined $att and defined $msg and @records) {
	  $msg_num++;
	  print handle_email_message($records[0]->{text},
				     ref => $ref,
				     msg_num => $msg_num,
				     att => $att,
				     msg => $msg,
				    );
	  exit 0;
     }
     my %seen_msg_ids;
     for my $record (@records) {
	  $msg_num++;
	  if ($skip_next) {
	       $skip_next = 0;
	       next;
	  }
	  $skip_next = 1 if $record->{type} eq 'html' and not $boring;
	  push @log, handle_record($record,$ref,$msg_num,\%seen_msg_ids);
     }
}

@log = reverse @log if $reverse;
$log = join("\n",@log);


# All of the below should be turned into a template

my %maintainer = %{getmaintainers()};
my %pkgsrc = %{getpkgsrc()};

my $indexentry;
my $showseverity;

my $tpack;
my $tmain;

my $dtime = strftime "%a, %e %b %Y %T UTC", gmtime;

unless (%status) {
    print $q->header(-type => "text/html",
		     -charset => 'utf-8',
		     (length $mtime)?(-last_modified => $mtime):(),
		    );
    print fill_in_template(template=>'cgi/no_such_bug',
			   variables => {modify_time => $dtime,
					 bug_num     => $ref,
					},
			  );
    exit 0;
}

#$|=1;

my %package;
my @packages = splitpackages($status{package});

foreach my $pkg (@packages) {
     $package{$pkg} = {maintainer => exists($maintainer{$pkg}) ? $maintainer{$pkg} : '(unknown)',
		       source     => exists($pkgsrc{$pkg}) ? $pkgsrc{$pkg} : '(unknown)',
		       package    => $pkg,
		      };
}

# fixup various bits of the status
$status{tags_array} = [sort(split(/\s+/, $status{tags}))];
$status{date_text} = strftime('%a, %e %b %Y %T UTC', gmtime($status{date}));
$status{mergedwith_array} = [split(/ /,$status{mergedwith})];


my $version_graph = '';
if (@{$status{found_versions}} or @{$status{fixed_versions}}) {
     $version_graph = q(<a href=").
	  html_escape(version_url(package => $status{package},
				  found => $status{found_versions},
				  fixed => $status{fixed_versions},
				 )
		     ).
	  q("><img alt="version graph" src=").
	  html_escape(version_url(package => $status{package},
				  found => $status{found_versions},
				  fixed => $status{fixed_versions},
				  width => 2,
				  height => 2,
				 )
		     ).
	  qq{"></a>};
}



my @blockedby= split(/ /, $status{blockedby});
$status{blockedby_array} = [];
if (@blockedby && $status{"pending"} ne 'fixed' && ! length($status{done})) {
    for my $b (@blockedby) {
        my %s = %{get_bug_status($b)};
        next if $s{"pending"} eq 'fixed' || length $s{done};
	push @{$status{blockedby_array}},{bug_num => $b, subject => $s{subject}, status => \%s};
   }
}

my @blocks= split(/ /, $status{blocks});
$status{blocks_array} = [];
if (@blocks && $status{"pending"} ne 'fixed' && ! length($status{done})) {
    for my $b (@blocks) {
        my %s = %{get_bug_status($b)};
        next if $s{"pending"} eq 'fixed' || length $s{done};
	push @{$status{blocks_array}}, {bug_num => $b, subject => $s{subject}, status => \%s};
    }
}

if ($buglog !~ m#^\Q$gSpoolDir/db#) {
     $status{archived} = 1;
}

my $descriptivehead = $indexentry;

print $q->header(-type => "text/html",
		 -charset => 'utf-8',
		 (length $mtime)?(-last_modified => $mtime):(),
		);

print fill_in_template(template => 'cgi/bugreport',
		       variables => {status => \%status,
				     package => \%package,
				     log           => $log,
				     bug_num       => $ref,
				     version_graph => $version_graph,
				     isstrongseverity => \&Debbugs::Status::isstrongseverity,
				     html_escape   => \&Debbugs::CGI::html_escape,
				     looks_like_number => \&Scalar::Util::looks_like_number,
				    },
		       hole_var  => {'&package_links' => \&Debbugs::CGI::package_links,
				     '&bug_links'     => \&Debbugs::CGI::bug_links,
				     '&version_url'   => \&Debbugs::CGI::version_url,
				     '&bug_url'       => \&Debbugs::CGI::bug_url,
				     '&strftime'      => \&POSIX::strftime,
				     '&maybelink'     => \&Debbugs::CGI::maybelink,
				    },
		      );
