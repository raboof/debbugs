# This module is part of debbugs, and is released
# under the terms of the GPL version 2, or any later version at your option.
# See the file README and COPYING for more information.
# Copyright 2007 by Don Armstrong <don@donarmstrong.com>.

package Debbugs::SOAP;

=head1 NAME

Debbugs::SOAP --

=head1 SYNOPSIS


=head1 DESCRIPTION


=head1 BUGS

None known.

=cut

use warnings;
use strict;
use vars qw($DEBUG %EXPORT_TAGS @EXPORT_OK @EXPORT);
use base qw(Exporter SOAP::Server::Parameters);

BEGIN{
     $DEBUG = 0 unless defined $DEBUG;

     @EXPORT = ();
     %EXPORT_TAGS = (
		    );
     @EXPORT_OK = ();
     Exporter::export_ok_tags();
     $EXPORT_TAGS{all} = [@EXPORT_OK];

}


use Debbugs::Status qw(get_bug_status);
use Debbugs::Common qw(make_list);
use Storable qw(nstore retrieve);
use Debbugs::Cookies;


our $CURRENT_VERSION = 1;
our %DEBBUGS_SOAP_COOKIES;


=head2 get_usertag

     my %ut = get_usertag('don@donarmstrong.com','this-bug-sucks','eat-this-bug');

Returns a hashref of bugs which have the specified usertags for the
user set.

=cut

use Debbugs::User qw(read_usertags);

sub get_usertag {
     my $VERSION = __populate_version(pop);
     my ($self,$email, @tags) = @_;
     my %ut = ();
     read_usertags(\%ut, $email);
     my %tags;
     @tags{@tags} = (1) x @tags;
     if (keys %tags > 0) {
	  for my $tag (keys %ut) {
	       delete $ut{$tag} unless exists $tags{$tag};
	  }
     }
     return \%ut;
}


use Debbugs::Status;

=head2 get_status 

     my @statuses = get_status(@bugs);

Returns an arrayref of hashrefs which output the status for specific
sets of bugs.

See L<Debbugs::Status::get_bug_status> for details.

=cut

sub get_status {
     my $VERSION = __populate_version(pop);
     my ($self,@bugs) = @_;
     @bugs = make_list(@bugs);

     my %status;
     for my $bug (@bugs) {
	  my $bug_status = get_bug_status(bug => $bug);
	  if (defined $bug_status and keys %{$bug_status} > 0) {
	       $status{$bug}  = $bug_status;
	  }
     }
#     __prepare_response($self);
     return \%status;
}

=head2 get_bugs

     my @bugs = get_bugs(...);

See L<Debbugs::Bugs::get_bugs> for details.

=cut

use Debbugs::Bugs qw();

sub get_bugs{
     my $VERSION = __populate_version(pop);
     my ($self,@params) = @_;
     my %params;
     while (my ($key,$value) = splice @params,0,2) {
	  push @{$params{$key}}, $value;
     }
     my @bugs;
     @bugs = Debbugs::Bugs::get_bugs(%params);
     return \@bugs;
}


=head1 VERSION COMPATIBILITY

The functionality provided by the SOAP interface will change over time.

To the greatest extent possible, we will attempt to provide backwards
compatibility with previous versions; however, in order to have
backwards compatibility, you need to specify the version with which
you are compatible.

=cut

sub __populate_version{
     my ($request) = @_;
     return $request->{___debbugs_soap_version};
}

1;


__END__





